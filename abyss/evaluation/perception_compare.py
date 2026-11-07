"""Compare ideal and real perception on the same worlds: the brief's perception ablation.

    python -m abyss.evaluation.perception_compare --manifest <split manifest> --artifact data/perception-expanded

Both modes are scored on true labels, so a difference shows what vision errors cost the
planner. Needs the perception package, PyTorch and a saved model. A small image pool
reuses each image often, so results describe that pool, not vision in general.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from ..config import SimConfig, load_config
from ..fathomnet_perception import load_fathomnet
from ..planners import PLANNERS
from ..run_mission import run_mission, validate_mission_log
from .benchmark import paired_ci

EVALUATION_SEEDS = tuple(range(1000, 1020))
WORLDS = (("ridge", 0.5), ("reversed", 0.5), ("random", 0.0))
COMPARED_PLANNERS = ("abyss", "frontier")


def compare(
    base: SimConfig, kit: dict, seeds=EVALUATION_SEEDS, worlds=WORLDS, planners=COMPARED_PLANNERS
) -> dict:
    """Run each planner in both modes and return a JSON-ready summary."""
    categories = len(kit["image_pool"].categories)
    groups = []
    missions = safe = 0
    model_name = kit["perception"].name
    for scenario, rho in worlds:
        ideal_config = replace(
            base, scenario=scenario, rho=rho, n_categories=categories, perception_mode="ideal"
        )
        real_config = replace(ideal_config, perception_mode="real")
        for name in planners:
            ideal, real, totals = [], [], {"images": 0, "familiar": 0, "correct": 0, "withheld": 0,
                                           "flagged": 0, "false_alerts": 0}
            for seed in seeds:
                log_i, reveal_i = run_mission(ideal_config, PLANNERS[name](), seed)
                log_r, reveal_r = run_mission(real_config, PLANNERS[name](), seed, **kit)
                for log in (log_i, log_r):
                    validate_mission_log(log)
                    missions += 1
                    safe += bool(log["outcome"]["safe_return"])
                ideal.append(reveal_i["true_distinct_count"])
                real.append(reveal_r["true_distinct_count"])
                for obs in reveal_r["true_observations"]:
                    for image in obs["images"]:
                        totals["images"] += 1
                        if image["withheld"]:
                            totals["withheld"] += 1
                            totals["flagged"] += image["is_unknown"]
                        else:
                            totals["familiar"] += 1
                            totals["false_alerts"] += image["is_unknown"]
                            totals["correct"] += (
                                not image["is_unknown"]
                                and image["predicted_category"] == image["true_category"]
                            )
            mean, low, high = paired_ci(np.array(real, float) - np.array(ideal, float))
            groups.append(
                {
                    "scenario": scenario,
                    "rho": rho,
                    "planner": name,
                    "ideal_mean": float(np.mean(ideal)),
                    "real_mean": float(np.mean(real)),
                    "real_minus_ideal": mean,
                    "ci95_low": low,
                    "ci95_high": high,
                    "images_shown": totals,
                }
            )
    return {
        "provenance": {
            "biology": "simulated",
            "perception_model": model_name,
            "metric": "true distinct categories within the energy budget",
            "note": "Image counts repeat images across surveys, so they are not a held-out evaluation.",
        },
        "seeds": list(seeds),
        "n_categories": categories,
        "safety": {"missions": missions, "safe_returns": safe},
        "results": groups,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--artifact", default="data/perception")
    parser.add_argument("--out", type=Path, default=Path("results/perception_comparison.json"))
    args = parser.parse_args()

    summary = compare(load_config(args.config), load_fathomnet(args.manifest, args.artifact))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    for row in summary["results"]:
        print(
            f"{row['scenario']} {row['rho']:g} {row['planner']}: ideal {row['ideal_mean']:.2f}, "
            f"real {row['real_mean']:.2f}, difference {row['real_minus_ideal']:+.2f} "
            f"[{row['ci95_low']:+.2f}, {row['ci95_high']:+.2f}]"
        )
    print(f"Safe returns: {summary['safety']['safe_returns']} of {summary['safety']['missions']}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
