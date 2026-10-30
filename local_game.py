"""Local simulator for the game API used by The Farmer Was Replaced.

This module is **local-only**.  The game's interpreter is a Python subset that
does not support classes, dataclasses or the standard library, so none of the
in-game files import this module.  ``run_local.py`` installs the API into
``builtins`` and then imports the unmodified game code.

The defaults below are based on the game wiki:

* 400 ticks per second
* harvest / plant / move / till: 200 ticks
* growth times: grass 0.5s, bush 3.2-4.8s, carrot 4.8-7.2s, tree 5.6-8.4s
* yields: grass 1 hay, bush 1 wood, tree 5 wood, carrot 1 carrot
* carrot planting costs 512 hay + 512 wood

Adjust ``CONFIG`` (or pass ``--config file.json`` to ``run_local.py``) to match
the unlock levels in your save.
"""

from __future__ import annotations

import builtins
import copy
import json
import random
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Game constants
# ---------------------------------------------------------------------------

class Items:
    Hay = "Hay"
    Wood = "Wood"
    Carrot = "Carrot"
    Water = "Water"
    Fertilizer = "Fertilizer"
    Power = "Power"
    Pumpkin = "Pumpkin"
    Cactus = "Cactus"
    Bone = "Bone"
    Gold = "Gold"


class Grounds:
    Grassland = "Grassland"
    Soil = "Soil"


class Entities:
    Grass = "Grass"
    Bush = "Bush"
    Tree = "Tree"
    Carrot = "Carrot"
    Pumpkin = "Pumpkin"
    Sunflower = "Sunflower"
    Cactus = "Cactus"


# Directions are (dx, dy) pairs.  North increases y.
North = (0, 1)
South = (0, -1)
East = (1, 0)
West = (-1, 0)

_DIRECTION_NAMES = {
    North: "North",
    South: "South",
    East: "East",
    West: "West",
}


CONFIG = {
    "ticks_per_second": 400,
    "action_ticks": 200,
    "query_ticks": 1,
    # Growth time ranges in seconds (min, max).
    "growth": {
        Entities.Grass: (0.5, 0.5),
        Entities.Bush: (3.2, 4.8),
        Entities.Carrot: (4.8, 7.2),
        Entities.Tree: (5.6, 8.4),
    },
    # Items produced by a successful harvest.
    "yields": {
        Entities.Grass: {Items.Hay: 1},
        Entities.Bush: {Items.Wood: 1},
        Entities.Tree: {Items.Wood: 5},
        Entities.Carrot: {Items.Carrot: 1},
    },
    # Items consumed by a successful plant.
    "plant_costs": {
        Entities.Grass: {},
        Entities.Bush: {},
        Entities.Tree: {},
        Entities.Carrot: {Items.Hay: 512, Items.Wood: 512},
    },
    # Ground types an entity can be planted on.
    "plantable_on": {
        Entities.Grass: {Grounds.Grassland, Grounds.Soil},
        Entities.Bush: {Grounds.Grassland, Grounds.Soil},
        Entities.Tree: {Grounds.Grassland, Grounds.Soil},
        Entities.Carrot: {Grounds.Soil},
    },
}


class SimulationLimit(Exception):
    """Raised when the simulator reaches a configured safety limit."""


@dataclass
class Cell:
    ground: str = Grounds.Grassland
    entity: str | None = None
    ready_at: int = 0


def _deep_update(target, updates):
    for key, value in updates.items():
        # An empty dict explicitly replaces (clears) the existing value, which
        # is useful for removing planting costs in a config file.
        if isinstance(value, dict) and value and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


def load_config(path):
    """Load a JSON config file and merge it over the defaults."""
    config = copy.deepcopy(CONFIG)
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return _deep_update(config, data)


class FarmSim:
    """A small, headless approximation of the farm."""

    def __init__(
        self,
        size=8,
        seed=0,
        max_ticks=100_000_000,
        max_calls=5_000_000,
        trace=False,
        config=None,
    ):
        self.size = max(1, int(size))
        self.rng = random.Random(seed)
        self.max_ticks = int(max_ticks)
        self.max_calls = int(max_calls)
        self.trace = bool(trace)
        self.config = copy.deepcopy(CONFIG) if config is None else config

        self.ticks_per_second = self.config["ticks_per_second"]
        self.action_ticks = self.config["action_ticks"]
        self.query_ticks = self.config["query_ticks"]

        self.grid = [[Cell() for _ in range(self.size)] for _ in range(self.size)]
        self.pos = (0, 0)
        self.tick = 0
        self.calls = 0

        # Incremented by every state-changing action.  Used by run_local.py to
        # detect an outer loop that keeps running without doing anything.
        self.state_version = 0

        self.inventory = {Items.Hay: 0, Items.Wood: 0, Items.Carrot: 0}
        self.stats = {
            "moves": 0,
            "harvests": 0,
            "plants": 0,
            "tills": 0,
            "harvested": {
                Entities.Grass: 0,
                Entities.Bush: 0,
                Entities.Tree: 0,
                Entities.Carrot: 0,
            },
            "planted": {
                Entities.Grass: 0,
                Entities.Bush: 0,
                Entities.Tree: 0,
                Entities.Carrot: 0,
            },
            "yields": {Items.Hay: 0, Items.Wood: 0, Items.Carrot: 0},
            "harvest_misses": 0,
            "plant_failures": {
                "occupied": 0,
                "wrong_ground": 0,
                "cost": 0,
            },
        }

        # The game starts with a farm full of mature grass.
        for row in self.grid:
            for cell in row:
                cell.ground = Grounds.Grassland
                cell.entity = Entities.Grass
                cell.ready_at = 0

    # -- helpers ---------------------------------------------------------

    def _current_cell(self):
        x, y = self.pos
        return self.grid[y][x]

    def _neighbors(self, x, y):
        for dx, dy in (North, South, East, West):
            yield (x + dx) % self.size, (y + dy) % self.size

    def _adjacent_trees(self, x, y):
        return sum(
            1
            for nx, ny in self._neighbors(x, y)
            if self.grid[ny][nx].entity == Entities.Tree
        )

    def _growth_ticks(self, entity, pos=None):
        low, high = self.config["growth"][entity]
        seconds = self.rng.uniform(low, high) if high > low else low
        ticks = max(1, int(round(seconds * self.ticks_per_second)))
        if entity == Entities.Tree and pos is not None:
            # Each adjacent tree doubles the growth time.
            ticks *= 2 ** self._adjacent_trees(*pos)
        return ticks

    def _schedule_grass(self, cell):
        if cell.ground == Grounds.Grassland and cell.entity is None:
            cell.entity = Entities.Grass
            cell.ready_at = self.tick + self._growth_ticks(Entities.Grass)

    def _enter(self, name, detail="", trace=False):
        self.calls += 1
        if self.calls > self.max_calls:
            raise SimulationLimit(
                f"call limit reached ({self.max_calls:,} API calls)"
            )
        if trace and self.trace:
            suffix = f" {detail}" if detail else ""
            print(f"[tick {self.tick:>10,}] {name}{suffix} at {self.pos}")

    def _leave(self, ticks):
        self.tick += ticks
        if self.tick > self.max_ticks:
            raise SimulationLimit(
                f"tick limit reached ({self.max_ticks:,} ticks)"
            )

    # -- queries ---------------------------------------------------------

    def get_world_size(self):
        self._enter("get_world_size")
        value = self.size
        self._leave(self.query_ticks)
        return value

    def get_ground_type(self):
        self._enter("get_ground_type")
        value = self._current_cell().ground
        self._leave(self.query_ticks)
        return value

    def get_entity_type(self):
        self._enter("get_entity_type")
        value = self._current_cell().entity
        self._leave(self.query_ticks)
        return value

    def get_pos_x(self):
        self._enter("get_pos_x")
        value = self.pos[0]
        self._leave(self.query_ticks)
        return value

    def get_pos_y(self):
        self._enter("get_pos_y")
        value = self.pos[1]
        self._leave(self.query_ticks)
        return value

    def get_tick_count(self):
        # Free in the game.
        self._enter("get_tick_count")
        return self.tick

    def get_time(self):
        # Free in the game.
        self._enter("get_time")
        return self.tick / self.ticks_per_second

    def num_items(self, item):
        self._enter("num_items", detail=str(item))
        value = self.inventory.get(item, 0)
        self._leave(self.query_ticks)
        return value

    def can_harvest(self):
        self._enter("can_harvest")
        cell = self._current_cell()
        value = cell.entity is not None and self.tick >= cell.ready_at
        self._leave(self.query_ticks)
        return value

    def can_move(self, direction):
        self._enter("can_move", detail=_DIRECTION_NAMES.get(direction, str(direction)))
        self._leave(self.query_ticks)
        return True

    def get_cost(self, thing):
        self._enter("get_cost", detail=str(thing))
        value = dict(self.config["plant_costs"].get(thing, {}))
        self._leave(self.query_ticks)
        return value

    def get_water(self):
        self._enter("get_water")
        self._leave(self.query_ticks)
        return 0.0

    # -- actions ---------------------------------------------------------

    def move(self, direction):
        self._enter(
            "move", detail=_DIRECTION_NAMES.get(direction, str(direction)), trace=True
        )
        try:
            dx, dy = direction
        except (TypeError, ValueError):
            self._leave(1)
            return False
        x, y = self.pos
        self.pos = ((x + dx) % self.size, (y + dy) % self.size)
        self.stats["moves"] += 1
        self.state_version += 1
        self._leave(self.action_ticks)
        return True

    def harvest(self):
        self._enter("harvest", trace=True)
        cell = self._current_cell()
        removed = cell.entity is not None

        if removed:
            entity = cell.entity
            mature = self.tick >= cell.ready_at
            if mature:
                for item, amount in self.config["yields"].get(entity, {}).items():
                    self.inventory[item] = self.inventory.get(item, 0) + amount
                    self.stats["yields"][item] = (
                        self.stats["yields"].get(item, 0) + amount
                    )
                self.stats["harvested"][entity] = (
                    self.stats["harvested"].get(entity, 0) + 1
                )
            cell.entity = None
            cell.ready_at = 0
            self._schedule_grass(cell)
            self.stats["harvests"] += 1
            self.state_version += 1
            self._leave(self.action_ticks)
        else:
            self.stats["harvest_misses"] += 1
            self._leave(1)

        return removed

    def plant(self, entity):
        self._enter("plant", detail=str(entity), trace=True)
        cell = self._current_cell()

        # Grass can be replaced by a new plant (the farm starts covered in
        # grass, and the first bush/tree is planted straight onto it).  Any
        # other existing plant blocks planting.
        if cell.entity is not None and cell.entity != Entities.Grass:
            self.stats["plant_failures"]["occupied"] += 1
            self._leave(1)
            return False

        allowed = self.config["plantable_on"].get(entity)
        if allowed is None or cell.ground not in allowed:
            self.stats["plant_failures"]["wrong_ground"] += 1
            self._leave(1)
            return False

        cost = self.config["plant_costs"].get(entity, {})
        if any(self.inventory.get(item, 0) < amount for item, amount in cost.items()):
            self.stats["plant_failures"]["cost"] += 1
            self._leave(1)
            return False

        for item, amount in cost.items():
            self.inventory[item] -= amount

        cell.entity = entity
        cell.ready_at = self.tick + self._growth_ticks(entity, self.pos)
        self.stats["plants"] += 1
        self.stats["planted"][entity] = self.stats["planted"].get(entity, 0) + 1
        self.state_version += 1
        self._leave(self.action_ticks)
        return True

    def till(self):
        self._enter("till", trace=True)
        cell = self._current_cell()

        if cell.ground == Grounds.Grassland:
            cell.ground = Grounds.Soil
            cell.entity = None
            cell.ready_at = 0
        else:
            cell.ground = Grounds.Grassland
            cell.entity = None
            cell.ready_at = 0
            self._schedule_grass(cell)

        self.stats["tills"] += 1
        self.state_version += 1
        self._leave(self.action_ticks)
        return None

    def clear(self):
        self._enter("clear", trace=True)
        for y in range(self.size):
            for x in range(self.size):
                cell = self.grid[y][x]
                cell.ground = Grounds.Grassland
                cell.entity = Entities.Grass
                cell.ready_at = self.tick
        self.pos = (0, 0)
        self.state_version += 1
        self._leave(self.action_ticks)
        return None

    def use_item(self, item, n=1):
        self._enter("use_item", detail=f"{item} x{n}", trace=True)
        success = self.inventory.get(item, 0) >= n
        if success:
            self.inventory[item] -= n
            self.state_version += 1
        self._leave(self.action_ticks if success else 1)
        return success

    def do_a_flip(self):
        self._enter("do_a_flip", trace=True)
        self._leave(self.ticks_per_second)
        return None

    def quick_print(self, *args):
        # Free in the game; prints to output.txt there.  Locally stdout is more
        # useful.
        self._enter("quick_print")
        print(*args)
        return None

    # -- reporting -------------------------------------------------------

    def summary(self):
        lines = [
            f"Ticks: {self.tick:,}  ({self.tick / self.ticks_per_second:,.2f}s game time)",
            f"API calls: {self.calls:,}",
            f"Position: {self.pos}",
            "Inventory:",
        ]
        for item in (Items.Hay, Items.Wood, Items.Carrot):
            lines.append(f"  {item:<8} {self.inventory.get(item, 0):>12,}")

        lines.append("Actions:")
        lines.append(
            "  moves={moves:,}  harvests={harvests:,}  plants={plants:,}  tills={tills:,}".format(
                **self.stats
            )
        )

        if self.stats["harvest_misses"]:
            lines.append(f"  harvest misses: {self.stats['harvest_misses']:,}")

        failures = {
            reason: count
            for reason, count in self.stats["plant_failures"].items()
            if count
        }
        if failures:
            lines.append("Plant failures:")
            for reason, count in failures.items():
                lines.append(f"  {reason:<14} {count:>12,}")

        lines.append("Harvested entities:")
        for entity, count in self.stats["harvested"].items():
            if count:
                lines.append(f"  {entity:<8} {count:>12,}")

        lines.append("Yields:")
        for item, amount in self.stats["yields"].items():
            if amount:
                lines.append(f"  {item:<8} {amount:>12,}")

        return "\n".join(lines)

    def farm_map(self):
        symbols = {
            None: ".",
            Entities.Grass: "g",
            Entities.Bush: "b",
            Entities.Tree: "t",
            Entities.Carrot: "c",
        }
        lines = []
        for y in range(self.size - 1, -1, -1):
            row = []
            for x in range(self.size):
                cell = self.grid[y][x]
                symbol = symbols.get(cell.entity, "?")
                if cell.ground == Grounds.Soil:
                    symbol = symbol.upper() if symbol != "." else "_"
                if (x, y) == self.pos:
                    symbol = "@"
                row.append(symbol)
            lines.append(" ".join(row))
        lines.append(
            "Legend: . empty grassland, _ empty soil, g grass, b bush, t tree, "
            "c carrot, uppercase = on soil, @ drone"
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Installation into builtins
# ---------------------------------------------------------------------------

_SIM = None


def install(sim=None, **kwargs):
    """Create (or use) a simulator and expose the game API via builtins."""
    global _SIM
    if sim is None:
        sim = FarmSim(**kwargs)
    _SIM = sim

    api = {
        "Items": Items,
        "Grounds": Grounds,
        "Entities": Entities,
        "North": North,
        "South": South,
        "East": East,
        "West": West,
        "num_items": sim.num_items,
        "get_world_size": sim.get_world_size,
        "get_ground_type": sim.get_ground_type,
        "get_entity_type": sim.get_entity_type,
        "can_harvest": sim.can_harvest,
        "can_move": sim.can_move,
        "harvest": sim.harvest,
        "till": sim.till,
        "plant": sim.plant,
        "move": sim.move,
        "get_pos_x": sim.get_pos_x,
        "get_pos_y": sim.get_pos_y,
        "get_tick_count": sim.get_tick_count,
        "get_time": sim.get_time,
        "get_cost": sim.get_cost,
        "get_water": sim.get_water,
        "clear": sim.clear,
        "use_item": sim.use_item,
        "do_a_flip": sim.do_a_flip,
        "quick_print": sim.quick_print,
    }
    for name, value in api.items():
        setattr(builtins, name, value)
    return sim


def get_sim():
    return _SIM
