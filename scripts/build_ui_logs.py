"""Run real missions and write the logs and manifest the replay UI loads.

    python -m scripts.build_ui_logs

Runs each planner listed below on one world of each type. The first planner listed
fills the left panel and the second fills the right. The seed is fixed in advance and
is not chosen by outcome.

    python -m scripts.build_ui_logs --oceans 8

also writes oceans for the next seeds (1001, 1002, ...), so the demo can switch to a new
hidden ocean where organisms are somewhere else. Extra oceans include only the main
comparison planners, to keep the files small. Seeds are consecutive and fixed in advance:
they are never picked by which planner wins.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from abyss.config import load_config
from abyss.landforms import LANDFORMS, landform_terrain
from abyss.planners import PLANNERS
from abyss.run_mission import run_mission, validate_mission_log

SCENARIOS = {"ridge": 0.5, "reversed": 0.5, "clustered": 1.0, "nonlinear": 1.0, "random": 0.0}
LANDFORM_SCENARIO = ("ridge", 0.5)
UI_PLANNERS = ("frontier", "abyss", "lawnmower", "heuristic", "random")
OCEAN_PLANNERS = ("frontier", "abyss", "lawnmower")
LABELS = {"abyss": "ABYSS"}


def _write_mission(config, name: str, seed: int, scenario: str, out_dir: Path) -> dict:
    log, reveal = run_mission(config, PLANNERS[name](), seed)
    validate_mission_log(log)
    stem = f"{log['world']['id']}-{name}"
    (out_dir / f"{stem}.json").write_text(json.dumps(log, separators=(",", ":")), encoding="utf-8")
    (out_dir / f"{stem}.reveal.json").write_text(
        json.dumps(reveal, separators=(",", ":")), encoding="utf-8"
    )
    return {
        "world_id": log["world"]["id"],
        "scenario": scenario,
        "rho": config.rho,
        "seed": seed,
        "planner": name,
        "label": LABELS.get(name, name.capitalize()),
        "log": f"logs/{stem}.json",
        "reveal": f"logs/{stem}.reveal.json",
    }


def build(config_path: str, out_dir: Path, seed: int, oceans: int = 1) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.json"):
        if old.name != "benchmark.json":
            old.unlink()

    base = load_config(config_path)
    worlds = [(scenario, rho, None) for scenario, rho in SCENARIOS.items()]
    shape = (base.height, base.width)
    worlds += [
        (*LANDFORM_SCENARIO, landform_terrain(name, shape, base.cell_size_m)) for name in LANDFORMS
    ]
    entries = []
    runs = [(seed, UI_PLANNERS)] + [(seed + n, OCEAN_PLANNERS) for n in range(1, oceans)]
    for scenario, rho in SCENARIOS.items():
        config = replace(base, scenario=scenario, rho=rho)
        for world_seed, planners in runs:
            for name in planners:
                entries.append(_write_mission(config, name, world_seed, scenario, out_dir))
    manifest = {"entries": entries}
    (out_dir / "index.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out", type=Path, default=Path("ui/logs"))
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--oceans", type=int, default=1, help="how many consecutive seeds to build")
    args = parser.parse_args()
    manifest = build(args.config, args.out, args.seed, args.oceans)
    print(f"Wrote {len(manifest['entries'])} missions to {args.out}")


if __name__ == "__main__":
    main()
