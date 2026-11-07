"""Development-seed grid search for ABYSS weights.

Uses seeds 0-19 only. Evaluation seeds (1000+) are never touched here, so the final
benchmark is not tuned on. Prints mean true distinct categories per scenario.

    python -m abyss.evaluation.tune
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace

import numpy as np

from ..config import SCENARIOS, load_config
from ..planners import PLANNERS
from ..planners.adaptive import AdaptivePlanner
from ..run_mission import run_mission

GRID = [
    {"beta": b, "gamma": g, "coverage": c}
    for b in (0.5, 1.0, 2.0)
    for g in (0.5, 1.0, 2.0)
    for c in ("spatial", "habitat", "both")
]
REFERENCES = ("lawnmower", "frontier", "heuristic")


def _score(job) -> float:
    config_path, planner, scenario, seeds = job
    config = replace(load_config(config_path), scenario=scenario)
    found = []
    for seed in seeds:
        if isinstance(planner, str):
            _, reveal = run_mission(config, PLANNERS[planner](), seed)
        else:
            _, reveal = run_mission(config, AdaptivePlanner(), seed, planner_config=planner)
        found.append(reveal["true_distinct_count"])
    return float(np.mean(found))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--seeds", type=int, default=20)
    a = ap.parse_args()
    if a.seeds > 1000:
        raise SystemExit("Tuning must stay on development seeds (< 1000)")
    seeds = tuple(range(a.seeds))
    candidates = [*GRID, *REFERENCES]
    jobs = [(a.config, p, s, seeds) for p in candidates for s in SCENARIOS]
    with ProcessPoolExecutor() as pool:
        scores = list(pool.map(_score, jobs))

    table: dict[str, dict[str, float]] = {}
    for (_, p, s, _), score in zip(jobs, scores):
        table.setdefault(str(p), {})[s] = score
    print(f"{'config':52s}" + "".join(f"{s[:9]:>10s}" for s in SCENARIOS) + "      mean")
    for name, row in sorted(table.items(), key=lambda kv: -np.mean(list(kv[1].values()))):
        print(f"{name:52s}" + "".join(f"{row[s]:10.2f}" for s in SCENARIOS)
              + f"{np.mean(list(row.values())):10.2f}")


if __name__ == "__main__":
    main()
