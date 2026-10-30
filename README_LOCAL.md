# Running the farm code locally

`main.py`, `cropsRequirement.py` and `eachCropFarmingTypes.py` are unchanged
game code. They are meant to be pasted into **The Farmer Was Replaced**, whose
interpreter is a Python subset (no classes, no `try`/`except`).

`local_game.py` + `run_local.py` provide a local simulator so the same code can
be tested outside the game.

## Usage

```bash
# Same settings as main.py (gap 20000)
./bin/python run_local.py

# Quick run with a small gap
./bin/python run_local.py --gap 20 --max-ticks 2000000 --show-farm

# Print every move/harvest/plant/till
./bin/python run_local.py --gap 20 --trace --show-farm
```

Useful options:

| Option | Default | Meaning |
|---|---:|---|
| `--size` | `8` | Farm side length |
| `--gap` | `20000` | Value passed to `farmingRequirements` |
| `--max-ticks` | `100000000` | Hard stop (400 ticks = 1 game second) |
| `--max-calls` | `5000000` | Hard stop on API calls |
| `--stall-iterations` | `200` | Stop if this many outer calls change nothing |
| `--seed` | `0` | Makes growth randomness repeatable |
| `--config` | none | JSON file overriding simulator values |
| `--trace` | off | Print state-changing actions |
| `--show-farm` | off | Print the final farm as ASCII |

## Simulator defaults

Based on the game wiki:

- 400 ticks/second; `harvest`/`plant`/`move`/`till` cost 200 ticks.
- Grass: 0.5 s, 1 hay.
- Bush: 3.2-4.8 s, 1 wood.
- Tree: 5.6-8.4 s, 5 wood, growth doubles per adjacent tree.
- Carrot: 4.8-7.2 s, 1 carrot, planted on soil, costs **512 hay + 512 wood**.
- Grass regrows automatically on grassland.
- Tilling toggles grassland/soil and destroys the plant on the tile.
- Movement wraps around the farm edges.

Your save's unlock levels change some of these numbers. Override them with a
JSON config, for example:

```json
{
  "yields": {
    "Grass": { "Hay": 8 },
    "Bush": { "Wood": 1 },
    "Tree": { "Wood": 5 },
    "Carrot": { "Carrot": 1 }
  },
  "plant_costs": {
    "Carrot": { "Hay": 512, "Wood": 512 }
  },
  "growth": {
    "Bush": [3.2, 4.8],
    "Carrot": [4.8, 7.2],
    "Tree": [5.6, 8.4]
  }
}
```

Then run:

```bash
./bin/python run_local.py --config my_config.json
```

## What the current code does in the simulator

Running with the default gap shows some real logic issues:

1. **Carrots are planted but never harvested before the next hay phase.**
   `farmingRequirements` counts `num_items(Items.Carrot)`, which only increases
   after a carrot is harvested. After one carrot sweep it sees 0 carrots and
   exits (or hits the hay/wood reserve check), leaving carrots growing.
2. **The next hay sweep tills the soil back to grassland**, destroying those
   growing carrots.
3. **Carrot planting costs 512 hay + 512 wood each.** The current target
   calculation only reserves about `2` hay/wood per carrot, so many
   `plant(Entities.Carrot)` calls fail with "not enough items". The simulator
   reports these as `Plant failures: cost`.
4. **Hay farming harvests whatever is on grassland**, so leftover trees/bushes
   are harvested for wood, not hay, until the farm is cleared.
5. **`cropYields` in `cropsRequirement.py` is unused.** It is defined but never
   read, so it does not affect the behaviour.

The `--config` option lets you test with your actual unlock levels (for example
higher grass yields) to see whether the logic behaves differently in your save.
