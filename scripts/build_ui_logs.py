"""Run real missions and write the logs and manifest the replay UI loads.

    python -m scripts.build_ui_logs

Every registered planner runs on the MVP worlds. While only one planner is registered,
it also gets a second run with a different planner seed, so the side-by-side view has
a genuine second mission on the same world.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from abyss.config import load_config
from abyss.planners import PLANNERS
from abyss.run_mission import planner_seed_for, run_mission, validate_mission_log

SCENARIOS = ("ridge", "reversed", "random")
RHO = {"ridge": 1.0, "reversed": 1.0, "random": 0.0}
SECOND_RUN_OFFSET = 1000


def build(config_path: str, out_dir: Path, seed: int) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.json"):
        old.unlink()

    base = load_config(config_path)
    entries = []
    for scenario in SCENARIOS:
        config = replace(base, scenario=scenario, rho=RHO[scenario])
        runs = [(name, planner_seed_for(seed), "") for name in sorted(PLANNERS)]
        if len(PLANNERS) == 1:
            name = runs[0][0]
            runs = [
                (name, planner_seed_for(seed), " (run 1)"),
                (name, planner_seed_for(seed + SECOND_RUN_OFFSET), " (run 2)"),
            ]
        for name, planner_seed, suffix in runs:
            log, reveal = run_mission(config, PLANNERS[name](), seed, planner_seed=planner_seed)
            validate_mission_log(log)
            stem = f"{log['world']['id']}-{name}-p{planner_seed}"
            (out_dir / f"{stem}.json").write_text(
                json.dumps(log, separators=(",", ":")), encoding="utf-8"
            )
            (out_dir / f"{stem}.reveal.json").write_text(
                json.dumps(reveal, separators=(",", ":")), encoding="utf-8"
            )
            entries.append(
                {
                    "world_id": log["world"]["id"],
                    "scenario": scenario,
                    "rho": config.rho,
                    "seed": seed,
                    "planner": name,
                    "label": f"{name.capitalize()}{suffix}",
                    "log": f"logs/{stem}.json",
                    "reveal": f"logs/{stem}.reveal.json",
                }
            )
    manifest = {"entries": entries}
    (out_dir / "index.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out", type=Path, default=Path("ui/logs"))
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    manifest = build(args.config, args.out, args.seed)
    print(f"Wrote {len(manifest['entries'])} missions to {args.out}")


if __name__ == "__main__":
    main()
