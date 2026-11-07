"""Separate, reproducible development and evaluation of the discovery variant.

python -m abyss.evaluation.discovery_experiment tune --workers 8
python -m abyss.evaluation.discovery_experiment run --workers 8
python -m abyss.evaluation.discovery_experiment landforms --workers 8
python -m abyss.evaluation.discovery_experiment vision --manifest ... --artifact ...
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
import json

import numpy as np

from ..config import load_config
from ..planners import PLANNERS
from ..planners.discovery import DISCOVERY_DEFAULTS
from ..run_mission import run_mission, validate_mission_log
from .benchmark import paired_ci
from .full_run import WORLDS, TERRAINS

DEVELOPMENT_SEEDS = tuple(range(10))
EVALUATION_SEEDS = tuple(range(3000, 3020))
DEVELOPMENT_WORLDS = (("random", 0.0), ("clustered", 1.0), ("ridge", 1.0),
                      ("reversed", 1.0), ("nonlinear", 1.0))
CANDIDATES = tuple({"rarity_power": power, "lookahead": depth}
                   for power in (0.0, 0.5, 1.0) for depth in (1, 3))
COMPARED = ("abyss-discovery", "abyss", "frontier", "lawnmower", "abyss-novelty",
            "abyss-discovery-nolearn", "abyss-discovery-norarity",
            "abyss-discovery-route", "abyss-discovery-nowarmup")


def _mission(job):
    config, name, seed, overrides, landform = job
    terrain = None
    if landform is not None:
        from ..landforms import landform_terrain
        terrain = landform_terrain(landform, (config.height, config.width), config.cell_size_m)
    log, reveal = run_mission(config, PLANNERS[name](), seed, planner_config=overrides, terrain=terrain)
    validate_mission_log(log)
    return _row(log, reveal, config, seed, overrides)


def _row(log, reveal, config, seed, overrides):
    outcome = log["outcome"]
    return {"terrain": log["provenance"]["terrain"], "scenario": config.scenario,
            "rho": config.rho, "seed": seed, "planner": log["planner"]["name"],
            "candidate": overrides, "distinct": reveal["true_distinct_count"],
            "available": reveal["categories_available_count"],
            "perceived": outcome["distinct_categories"], "surveys": outcome["surveys"],
            "energy": outcome["energy_used"], "safe": outcome["safe_return"],
            "forced": outcome["forced_return"]}


def tune(base, workers):
    jobs = [(replace(base, terrain_source=terrain, scenario=scenario, rho=rho),
             "abyss-discovery", seed, candidate, None)
            for candidate in CANDIDATES for terrain in TERRAINS
            for scenario, rho in DEVELOPMENT_WORLDS for seed in DEVELOPMENT_SEEDS]
    rows = _parallel(jobs, workers)
    table = []
    for candidate in CANDIDATES:
        selected = [r for r in rows if r["candidate"] == candidate]
        groups = {}
        for row in selected:
            groups.setdefault(f'{row["terrain"]}/{row["scenario"]}', []).append(row["distinct"])
        means = {key: float(np.mean(values)) for key, values in groups.items()}
        table.append({"config": candidate, "mean": float(np.mean(list(means.values()))), "world_means": means})
    best = max(table, key=lambda r: r["mean"])
    return {"seeds": list(DEVELOPMENT_SEEDS), "candidates": table, "selected": best["config"],
            "selection": "Equal weight for each development setting; first candidate breaks exact ties.",
            "rows": rows}


def _parallel(jobs, workers):
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = []
        for row in pool.map(_mission, jobs, chunksize=2):
            rows.append(row)
            if len(rows) % 100 == 0:
                print(f"Completed {len(rows)}/{len(jobs)} missions", flush=True)
        return rows


def _compare(reference, other):
    diff = np.asarray(reference, float) - np.asarray(other, float)
    mean, low, high = paired_ci(diff)
    return {"mean_difference": mean, "ci95_low": low, "ci95_high": high,
            "wins": int((diff > 0).sum()), "ties": int((diff == 0).sum()), "losses": int((diff < 0).sum())}


def summarise(rows, *, perception="ideal", artifact=None):
    """Pair within each setting/seed; aggregate by whole seed, not independent worlds."""
    groups = {}
    expected_planners = {row["planner"] for row in rows}
    for row in rows:
        groups.setdefault((row["terrain"], row["scenario"], row["rho"]), []).append(row)
    worlds = []
    for (terrain, scenario, rho), group in groups.items():
        by = {}
        for row in group:
            if row["seed"] in by.get(row["planner"], {}):
                raise ValueError("Unpaired experiment: duplicate planner/setting/seed")
            by.setdefault(row["planner"], {})[row["seed"]] = row
        if set(by) != expected_planners:
            raise ValueError("Unpaired experiment: missing planner in a setting")
        seeds = sorted(by["abyss-discovery"])
        if any(set(entries) != set(seeds) for entries in by.values()):
            raise ValueError("Unpaired experiment: each planner must have the same seeds")
        values = {p: [d[s]["distinct"] for s in seeds] for p, d in by.items()}
        worlds.append({"terrain": terrain, "scenario": scenario, "rho": rho,
                       "means": {p: float(np.mean(v)) for p, v in values.items()},
                       "surveys": {p: float(np.mean([d[s]["surveys"] for s in seeds])) for p, d in by.items()},
                       "discovery_vs": {p: _compare(values["abyss-discovery"], v) for p, v in values.items()
                                        if p != "abyss-discovery"}})
    seed_values = {}
    for row in rows:
        seed_values.setdefault(row["planner"], {}).setdefault(row["seed"], []).append(row["distinct"])
    seeds = sorted(seed_values["abyss-discovery"])
    values = {p: [float(np.mean(d[s])) for s in seeds] for p, d in seed_values.items()}
    return {"provenance": {"biology": "simulated", "perception": perception,
                           "artifact": artifact, "metric": "true distinct categories within fixed budget",
                           "interval": "95% paired seed bootstrap; aggregate resamples complete seeds",
                           "status": "Experimental; does not replace the published benchmark."},
            "seeds": seeds, "frozen_config": DISCOVERY_DEFAULTS,
            "safety": {"missions": len(rows), "safe_returns": sum(r["safe"] for r in rows),
                       "forced_returns": sum(r["forced"] for r in rows)},
            "aggregate": {"means": {p: float(np.mean(v)) for p, v in values.items()},
                          "discovery_vs": {p: _compare(values["abyss-discovery"], v) for p, v in values.items()
                                           if p != "abyss-discovery"}},
            "worlds": worlds, "rows": rows}


def render(data):
    safety, aggregate = data["safety"], data["aggregate"]
    lines = ["# Experimental category-aware discovery planner", "",
             "Generated from recorded matched missions; every world setting is included.", "",
             f'Perception: {data["provenance"]["perception"]}. Biology is simulated. '
             f'Seeds: {data["seeds"][0]}–{data["seeds"][-1]}.', "",
             f'{safety["safe_returns"]}/{safety["missions"]} safe returns; '
             f'{safety["forced_returns"]} forced returns.', "",
             "The discovery score is a rare-habitat proxy, not a calibrated number of unseen species. "
             "Fewer surveys are not themselves success. Original ABYSS and Frontier are unchanged.", "",
             "| Planner | Mean true categories | Mean perceived labels | Mean survey stops | Discovery minus planner [95% CI] |",
             "| --- | --- | --- | --- | --- |"]
    for planner, mean in aggregate["means"].items():
        comparison = aggregate["discovery_vs"].get(planner)
        delta = "—" if comparison is None else (
            f'{comparison["mean_difference"]:+.2f} [{comparison["ci95_low"]:+.2f}, {comparison["ci95_high"]:+.2f}]')
        observed = [r for r in data["rows"] if r["planner"] == planner]
        perceived = float(np.mean([r["perceived"] for r in observed]))
        surveys = float(np.mean([r["surveys"] for r in observed]))
        lines.append(f"| {planner} | {mean:.2f} | {perceived:.2f} | {surveys:.2f} | {delta} |")
    lines += ["", "Intervals resample whole seeds across settings. No multiple-comparison correction; "
              "these estimates do not prove general superiority or real-ocean performance.", "",
              "| Terrain | Ecology / signal | Discovery | ABYSS | Frontier | Discovery − Frontier [95% CI] |",
              "| --- | --- | --- | --- | --- | --- |"]
    for world in data["worlds"]:
        means, c = world["means"], world["discovery_vs"]["frontier"]
        lines.append(f'| {world["terrain"]} | {world["scenario"]} / {world["rho"]:g} | '
                     f'{means["abyss-discovery"]:.2f} | {means["abyss"]:.2f} | {means["frontier"]:.2f} | '
                     f'{c["mean_difference"]:+.2f} [{c["ci95_low"]:+.2f}, {c["ci95_high"]:+.2f}] |')
    lines += ["", "All per-mission scores, perceived counts, survey counts, available categories, energy and "
              "safety are retained in the accompanying JSON. See [the protocol](discovery-protocol.md) "
              "and [implementation and usage](discovery-planner.md).", ""]
    return "\n".join(lines)


def write_results(path, data):
    """Keep metadata readable and each mission on one line for reviewable diffs."""
    metadata = {key: value for key, value in data.items() if key != "rows"}
    header = json.dumps(metadata, indent=2).rstrip()[:-1]
    records = ",\n".join("    " + json.dumps(row, separators=(",", ":")) for row in data["rows"])
    Path(path).write_text(header.rstrip() + ',\n  "rows": [\n' + records + '\n  ]\n}\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("tune", "run", "landforms", "vision", "report"))
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--manifest")
    parser.add_argument("--artifact")
    args = parser.parse_args()
    base = load_config(args.config)
    stem = {"run": "evaluation", "tune": "development"}.get(args.command, args.command)
    out = args.out or Path(f'docs/discovery-{stem}.json')
    if args.command == "report":
        if args.out is None:
            parser.error("report requires --out pointing at an existing results JSON")
        data = json.loads(out.read_text())
    elif args.command == "tune":
        data = tune(base, args.workers)
        print(f'Selected {data["selected"]}', flush=True)
    elif args.command == "vision":
        if not args.manifest or not args.artifact:
            parser.error("vision requires --manifest and --artifact")
        from ..fathomnet_perception import load_fathomnet
        kit = load_fathomnet(args.manifest, args.artifact)
        base = replace(base, perception_mode="real", n_categories=len(kit["image_pool"].categories))
        rows = []
        compared = ("abyss-discovery", "abyss", "frontier", "abyss-discovery-unguarded")
        for scenario, rho in DEVELOPMENT_WORLDS:
            config = replace(base, scenario=scenario, rho=rho)
            for seed in EVALUATION_SEEDS[:3]:
                for name in compared:
                    log, reveal = run_mission(config, PLANNERS[name](), seed, **kit)
                    validate_mission_log(log)
                    rows.append(_row(log, reveal, config, seed, {}))
                    # Don't retain image evidence for this numerical experiment.
                    if hasattr(kit["perception"], "evidence_records"):
                        kit["perception"].evidence_records.clear()
                print(f"Completed {scenario}, seed {seed}", flush=True)
        data = summarise(rows, perception=kit["perception"].name,
                         artifact={"name": Path(args.artifact).name,
                                   "id": kit["perception"]._model.artifact_id})
    else:
        jobs = []
        if args.command == "landforms":
            from ..landforms import LANDFORMS
            settings = [(base.terrain_source, scenario, rho, name)
                        for name in LANDFORMS for scenario, rho in DEVELOPMENT_WORLDS]
            seeds, compared = EVALUATION_SEEDS[:5], COMPARED[:3]
        else:
            settings = [(terrain, scenario, rho, None) for terrain in TERRAINS for scenario, rho in WORLDS]
            seeds, compared = EVALUATION_SEEDS, COMPARED
        for terrain, scenario, rho, landform in settings:
            config = replace(base, terrain_source=terrain, scenario=scenario, rho=rho)
            jobs.extend((config, name, seed, {}, landform) for seed in seeds for name in compared)
        data = summarise(_parallel(jobs, args.workers))
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.command != "report":
        data["simulation"] = base.to_dict()
        write_results(out, data)
    if args.command != "tune":
        out.with_suffix(".md").write_text(render(data))
    print(f"Wrote {out}", flush=True)


if __name__ == "__main__":
    main()
