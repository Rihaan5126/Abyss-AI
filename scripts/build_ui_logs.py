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
from abyss.planners import PLANNERS, PLANNER_LABELS
from abyss.run_mission import run_mission, validate_mission_log

SCENARIOS = {"ridge": 0.5, "reversed": 0.5, "clustered": 1.0, "nonlinear": 1.0, "random": 0.0}
# The demo opens on ridge-associated ecology at full signal, where the 50-seed benchmark
# shows ABYSS's largest gain. The world type was chosen from the benchmark, not the seed.
HEADLINE = ("ridge", 1.0)
LANDFORM_SCENARIO = ("ridge", 0.5)
UI_PLANNERS = ("frontier", "abyss", "lawnmower", "heuristic", "random")
OCEAN_PLANNERS = ("frontier", "abyss", "lawnmower")
LABELS = PLANNER_LABELS


def _write_mission(config, name: str, seed: int, scenario: str, out_dir: Path, terrain=None, prefix="logs") -> dict:
    log, reveal = run_mission(config, PLANNERS[name](), seed, terrain=terrain)
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
        "terrain": log["provenance"]["terrain"],
        "planner": name,
        "label": LABELS.get(name, name.capitalize()),
        "log": f"{prefix}/{stem}.json",
        "reveal": f"{prefix}/{stem}.reveal.json",
    }


def build(config_path: str, out_dir: Path, seed: int, oceans: int = 1, planners=None) -> dict:
    if planners is not None and (not planners or len(set(planners)) != len(planners)
                                 or any(p not in PLANNERS for p in planners)):
        raise ValueError("planners must contain unique registered planner names")
    if not isinstance(oceans, int) or not 1 <= oceans <= 20:
        raise ValueError("oceans must be an integer between 1 and 20")
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.json"):
        if old.name != "benchmark.json":
            old.unlink()

    base = load_config(config_path)
    worlds = [(*HEADLINE, None)] + [(scenario, rho, None) for scenario, rho in SCENARIOS.items()]
    shape = (base.height, base.width)
    worlds += [
        (*LANDFORM_SCENARIO, landform_terrain(name, shape, base.cell_size_m)) for name in LANDFORMS
    ]
    entries = []
    runs = [(seed, planners or UI_PLANNERS)] + [(seed + n, planners or OCEAN_PLANNERS) for n in range(1, oceans)]
    try:
        prefix = out_dir.resolve().relative_to(Path("ui").resolve()).as_posix()
    except ValueError:
        prefix = out_dir.name
    for scenario, rho, terrain in worlds:
        config = replace(base, scenario=scenario, rho=rho)
        # Preserve the current demo's smaller ideal landform set.
        for world_seed, selected in runs if terrain is None else runs[:1]:
            for name in selected:
                entries.append(_write_mission(config, name, world_seed, scenario, out_dir, terrain, prefix))
    manifest = {"entries": entries}
    (out_dir / "index.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out", type=Path, default=Path("ui/logs"))
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--oceans", type=int, default=1, help="how many consecutive seeds to build")
    parser.add_argument("--planners", nargs="+", choices=sorted(PLANNERS),
                        help="Optional experimental comparison; original defaults are preserved")
    args = parser.parse_args()
    manifest = build(args.config, args.out, args.seed, args.oceans, args.planners)
    print(f"Wrote {len(manifest['entries'])} missions to {args.out}")


if __name__ == "__main__":
    main()
