"""Run the frozen benchmark across every world setting and write the results files.

    python -m abyss.evaluation.full_run

Uses Cam's ``run_benchmark`` and paired intervals, on evaluation seeds (1000+) only, in
parallel. Writes ``results/benchmark.csv`` for the charts and ``ui/logs/benchmark.json``
for the replay UI. Every world below is reported, whichever planner does best.
"""

from __future__ import annotations

import argparse
import csv
import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np

from ..config import SimConfig, load_config
from ..planners.adaptive import DEFAULTS
from .benchmark import DEFAULT_PLANNERS, paired_ci, run_benchmark

EVALUATION_SEEDS = tuple(range(1000, 1050))
WORLDS = (
    ("random", 0.0),
    ("clustered", 1.0),
    ("ridge", 0.25),
    ("ridge", 0.5),
    ("ridge", 1.0),
    ("reversed", 0.25),
    ("reversed", 0.5),
    ("reversed", 1.0),
    ("nonlinear", 1.0),
)
TERRAINS = ("gebco", "synthetic")
OTHERS = tuple(p for p in DEFAULT_PLANNERS if p != "abyss")


def _run_block(job: tuple) -> list[dict]:
    config, scenario, rho, seeds = job
    rows = run_benchmark(config, [scenario], seeds, DEFAULT_PLANNERS, rho)
    return [{"terrain": config.terrain_source, **row} for row in rows]


def _jobs(base: SimConfig, seeds) -> list[tuple]:
    return [
        (replace(base, terrain_source=terrain), scenario, rho, (seed,))
        for terrain in TERRAINS
        for scenario, rho in WORLDS
        for seed in seeds
    ]


def summarise_world(rows: list[dict]) -> dict:
    first = rows[0]
    by_planner: dict[str, dict[int, float]] = {}
    surveys: dict[str, list[float]] = {}
    for row in rows:
        by_planner.setdefault(row["planner"], {})[row["seed"]] = row["distinct_categories"]
        surveys.setdefault(row["planner"], []).append(row["surveys"])
    seeds = sorted(by_planner["abyss"])
    values = {p: np.array([by_planner[p][s] for s in seeds], float) for p in by_planner}

    comparisons = {}
    for other in OTHERS:
        difference = values["abyss"] - values[other]
        mean, low, high = paired_ci(difference)
        comparisons[other] = {
            "mean_difference": mean,
            "ci95_low": low,
            "ci95_high": high,
            "wins": int((difference > 0).sum()),
            "ties": int((difference == 0).sum()),
            "losses": int((difference < 0).sum()),
        }
    return {
        "terrain": first["terrain"],
        "scenario": first["scenario"],
        "rho": first["rho"],
        "planners": {
            p: {
                "mean": float(v.mean()),
                "std": float(v.std(ddof=1)),
                "surveys_mean": float(np.mean(surveys[p])),
            }
            for p, v in values.items()
        },
        "abyss_vs": comparisons,
    }


def summarise_all(rows: list[dict], seeds, simulation: dict) -> dict:
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((row["terrain"], row["scenario"], row["rho"]), []).append(row)
    return {
        "provenance": {
            "biology": "simulated",
            "energy": "abstract units",
            "metric": "distinct categories found within the energy budget, scored on true labels",
            "perception": "ideal: labels come directly from the simulator",
            "interval": "95% paired bootstrap across seeds on shared worlds",
            "note": "GEBCO runs share one terrain crop, so they show no regional generalisation",
        },
        "seeds": list(seeds),
        "frozen_config": {"abyss": DEFAULTS, "simulation": simulation},
        "safety": {
            "missions": len(rows),
            "safe_returns": sum(bool(r["safe_return"]) for r in rows),
            "forced_returns": sum(bool(r["forced_return"]) for r in rows),
        },
        "worlds": [summarise_world(group) for group in groups.values()],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--csv", type=Path, default=Path("results/benchmark.csv"))
    parser.add_argument("--ui-out", type=Path, default=Path("ui/logs/benchmark.json"))
    parser.add_argument("--workers", type=int)
    args = parser.parse_args()

    base = load_config(args.config)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = [r for block in pool.map(_run_block, _jobs(base, EVALUATION_SEEDS)) for r in block]

    summary = summarise_all(rows, EVALUATION_SEEDS, base.to_dict())
    args.ui_out.parent.mkdir(parents=True, exist_ok=True)
    args.ui_out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with open(args.csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    safety = summary["safety"]
    print(f"{safety['missions']} missions. Safe returns: {safety['safe_returns']}")


if __name__ == "__main__":
    main()
