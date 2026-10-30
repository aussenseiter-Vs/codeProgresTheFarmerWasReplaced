#!/usr/bin/env python3
"""Run the farm code locally against the simulated game API.

The game files (``main.py``, ``cropsRequirement.py``,
``eachCropFarmingTypes.py``) are left untouched so they can still be pasted
into the game.  This runner installs the simulated API, imports the game code
and executes the same infinite loop as ``main.py`` with safety limits.

Examples::

    ./bin/python run_local.py --gap 20 --max-ticks 500000
    ./bin/python run_local.py --gap 20000 --show-farm
    ./bin/python run_local.py --gap 20 --trace --show-farm
"""

from __future__ import annotations

import argparse
import traceback

import local_game


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run The Farmer Was Replaced farm code locally."
    )
    parser.add_argument(
        "--size", type=int, default=8, help="farm side length (default: 8)"
    )
    parser.add_argument(
        "--gap",
        type=int,
        default=20000,
        help="gap passed to farmingRequirements (default: 20000, same as main.py)",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=100_000_000,
        help="stop after this many game ticks (default: 100,000,000)",
    )
    parser.add_argument(
        "--max-calls",
        type=int,
        default=5_000_000,
        help="stop after this many API calls (default: 5,000,000)",
    )
    parser.add_argument(
        "--stall-iterations",
        type=int,
        default=200,
        help=(
            "stop after this many consecutive farmingRequirements calls that "
            "change no farm state (default: 200)"
        ),
    )
    parser.add_argument(
        "--seed", type=int, default=0, help="random seed (default: 0)"
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="JSON file with CONFIG overrides (yields, costs, growth times, ...)",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="print every state-changing action (move/harvest/plant/till)",
    )
    parser.add_argument(
        "--show-farm",
        action="store_true",
        help="print an ASCII map of the farm at the end",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="only print the final summary"
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    config = local_game.load_config(args.config) if args.config else None
    sim = local_game.FarmSim(
        size=args.size,
        seed=args.seed,
        max_ticks=args.max_ticks,
        max_calls=args.max_calls,
        trace=args.trace,
        config=config,
    )
    local_game.install(sim)

    # Import after install: cropsRequirement.py reads Items at module level.
    from cropsRequirement import farmingRequirements

    if not args.quiet:
        print(
            f"Local farm simulator: size={args.size}, gap={args.gap}, "
            f"seed={args.seed}"
        )
        print(
            f"Limits: {args.max_ticks:,} ticks, {args.max_calls:,} API calls, "
            f"{args.stall_iterations} stall iterations"
        )
        print()

    stop_reason = "completed"
    outer = 0
    last_version = sim.state_version
    idle = 0

    try:
        while True:
            outer += 1
            farmingRequirements(args.gap)

            if sim.state_version == last_version:
                idle += 1
                if idle >= args.stall_iterations:
                    stop_reason = (
                        f"stalled: {idle} farmingRequirements calls in a row "
                        f"changed no farm state (gap={args.gap})"
                    )
                    break
            else:
                idle = 0
                last_version = sim.state_version
    except local_game.SimulationLimit as exc:
        stop_reason = str(exc)
    except KeyboardInterrupt:
        stop_reason = "interrupted"
    except Exception:
        stop_reason = "error"
        traceback.print_exc()

    print()
    print(f"Stopped: {stop_reason}")
    print(f"farmingRequirements calls: {outer:,}")
    print()
    print(sim.summary())

    if args.show_farm:
        print()
        print("Farm map (north is up):")
        print(sim.farm_map())

    return 0 if stop_reason != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
