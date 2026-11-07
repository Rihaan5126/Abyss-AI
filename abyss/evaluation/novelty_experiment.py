"""Test the experimental novelty planner, kept separate from the official benchmark.

    python -m abyss.evaluation.novelty_experiment tune   # development seeds 0-19
    python -m abyss.evaluation.novelty_experiment run    # fresh seeds 2000-2049

Seeds 1000+ informed the idea for this planner, so the final run uses seeds no planner has
been judged on. Tuning never touches them. This writes its own results file and leaves
ui/logs/benchmark.json and docs/results.md alone.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np

from ..config import load_config
from ..planners import PLANNERS
from ..planners.novelty import NOVELTY_DEFAULTS
from ..run_mission import run_mission, validate_mission_log
from .benchmark import paired_ci
from .full_run import TERRAINS, WORLDS

DEVELOPMENT_SEEDS = tuple(range(20))
FRESH_SEEDS = tuple(range(2000, 2050))
FORGETTING_GRID = (0.6, 0.75, 0.85, 0.9, 0.95, 1.0)
TUNING_WORLDS = (("random", 0.0), ("clustered", 1.0), ("ridge", 1.0), ("reversed", 1.0), ("nonlinear", 1.0))
COMPARED = ("abyss-novelty", "abyss", "frontier", "lawnmower")


def _mission(job: tuple) -> dict:
    config, name, seed, planner_config = job
    log, reveal = run_mission(config, PLANNERS[name](), seed, planner_config=planner_config)
    validate_mission_log(log)
    return {
        "terrain": config.terrain_source,
        "scenario": config.scenario,
        "rho": config.rho,
        "seed": seed,
        "planner": name,
        "distinct": reveal["true_distinct_count"],
        "safe": log["outcome"]["safe_return"],
        "surveys": log["outcome"]["surveys"],
    }


def tune(base, workers=None) -> list[dict]:
    jobs = []
    for forgetting in FORGETTING_GRID:
        for scenario, rho in TUNING_WORLDS:
            config = replace(base, terrain_source="gebco", scenario=scenario, rho=rho)
            for seed in DEVELOPMENT_SEEDS:
                jobs.append((config, "abyss-novelty", seed, {"forgetting": forgetting}))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(_mission, jobs, chunksize=8))
    table = []
    for n, forgetting in enumerate(FORGETTING_GRID):
        chunk = rows[n * len(TUNING_WORLDS) * len(DEVELOPMENT_SEEDS):][: len(TUNING_WORLDS) * len(DEVELOPMENT_SEEDS)]
        by_world = {}
        for row in chunk:
            by_world.setdefault(row["scenario"], []).append(row["distinct"])
        means = {world: float(np.mean(values)) for world, values in by_world.items()}
        table.append({"forgetting": forgetting, "mean": float(np.mean(list(means.values()))), **means})
    return table


def summarise(rows: list[dict], seeds) -> dict:
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((row["terrain"], row["scenario"], row["rho"]), []).append(row)
    worlds = []
    for (terrain, scenario, rho), group in groups.items():
        by_planner = {}
        for row in group:
            by_planner.setdefault(row["planner"], {})[row["seed"]] = row["distinct"]
        order = sorted(by_planner["abyss-novelty"])
        values = {p: np.array([by_planner[p][s] for s in order], float) for p in by_planner}
        comparisons = {}
        for other in COMPARED[1:]:
            mean, low, high = paired_ci(values["abyss-novelty"] - values[other])
            comparisons[other] = {"mean_difference": mean, "ci95_low": low, "ci95_high": high}
        worlds.append(
            {
                "terrain": terrain,
                "scenario": scenario,
                "rho": rho,
                "means": {p: float(v.mean()) for p, v in values.items()},
                "novelty_vs": comparisons,
            }
        )
    return {
        "provenance": {
            "status": "Experimental planner, separate from the official benchmark.",
            "biology": "simulated",
            "perception": "ideal: labels come directly from the simulator",
            "metric": "true distinct categories within the energy budget",
        },
        "seeds": list(seeds),
        "frozen_config": NOVELTY_DEFAULTS,
        "safety": {"missions": len(rows), "safe_returns": sum(bool(r["safe"]) for r in rows)},
        "worlds": worlds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("tune", "run"))
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--out", type=Path, default=Path("results/novelty_experiment.json"))
    args = parser.parse_args()
    base = load_config(args.config)

    if args.command == "tune":
        for row in sorted(tune(base, args.workers), key=lambda r: -r["mean"]):
            print({k: round(v, 2) for k, v in row.items()})
        return

    jobs = [
        (replace(base, terrain_source=terrain, scenario=scenario, rho=rho), name, seed, {})
        for terrain in TERRAINS
        for scenario, rho in WORLDS
        for name in COMPARED
        for seed in FRESH_SEEDS
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(_mission, jobs, chunksize=16))
    summary = summarise(rows, FRESH_SEEDS)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"{summary['safety']['missions']} missions, {summary['safety']['safe_returns']} safe. Wrote {args.out}")


if __name__ == "__main__":
    main()
