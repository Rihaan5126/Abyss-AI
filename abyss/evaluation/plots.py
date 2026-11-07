"""Benchmark charts for the presentation, drawn only from executed results.

    python -m abyss.evaluation.benchmark --seeds 20 --out results/benchmark.csv
    python -m abyss.evaluation.plots --csv results/benchmark.csv --out results/figures

Charts:
  distinct_by_scenario.png  mean true distinct categories per planner, 95% CI over seeds
  paired_difference.png     ABYSS minus each planner, paired 95% bootstrap CI
  discovery_curves.png      mean cumulative true discoveries against energy spent
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ..config import SCENARIOS, load_config  # noqa: E402
from ..planners import PLANNERS  # noqa: E402
from ..run_mission import run_mission  # noqa: E402
from .benchmark import paired_ci  # noqa: E402

# Colour follows the planner, never its rank, so every chart uses the same mapping.
COLORS = {
    "abyss": "#2a78d6",
    "frontier": "#eb6834",
    "heuristic": "#1baf7a",
    "lawnmower": "#eda100",
    "random": "#e87ba4",
    "abyss-nolearn": "#008300",
    "abyss-noinfo": "#6250d6",
}
MARKERS = {"abyss": "o", "frontier": "s", "heuristic": "^", "lawnmower": "D",
           "random": "v", "abyss-nolearn": "P", "abyss-noinfo": "X"}
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def load_rows(path: str | Path) -> list[dict]:
    with open(path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    for r in rows:
        r["seed"] = int(r["seed"])
        r["distinct_categories"] = float(r["distinct_categories"])
    return rows


def _values(rows, scenario, planner) -> dict[int, float]:
    return {r["seed"]: r["distinct_categories"] for r in rows
            if r["scenario"] == scenario and r["planner"] == planner}


def _scenarios(rows) -> list[str]:
    present = {r["scenario"] for r in rows}
    return [s for s in SCENARIOS if s in present]


def _planners(rows) -> list[str]:
    present = dict.fromkeys(r["planner"] for r in rows)
    return [p for p in COLORS if p in present] + [p for p in present if p not in COLORS]


def plot_distinct(rows, out: Path, planners=None) -> Path:
    scenarios = _scenarios(rows)
    planners = planners or [p for p in _planners(rows) if not p.startswith("abyss-")]
    fig, ax = plt.subplots(figsize=(8, 0.9 * len(scenarios) + 1.4), facecolor=SURFACE)
    _style(ax)
    offsets = np.linspace(-0.3, 0.3, len(planners))
    for off, planner in zip(offsets, planners):
        means, lows, highs = [], [], []
        for s in scenarios:
            v = np.array(list(_values(rows, s, planner).values()))
            sem = v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else 0.0
            means.append(v.mean())
            lows.append(1.96 * sem)
            highs.append(1.96 * sem)
        y = np.arange(len(scenarios)) + off
        ax.errorbar(means, y, xerr=[lows, highs], fmt=MARKERS.get(planner, "o"), ms=7,
                    color=COLORS.get(planner, INK_2), ecolor=COLORS.get(planner, INK_2),
                    elinewidth=2, capsize=0, mec=SURFACE, mew=1.5, label=planner)
    ax.set_yticks(range(len(scenarios)), scenarios, color=INK)
    ax.invert_yaxis()
    ax.set_xlabel("True distinct organism categories found (mean, 95% CI over seeds)", color=INK_2)
    ax.set_title("Categories discovered on the same energy budget", loc="left", color=INK)
    ax.legend(frameon=False, ncol=len(planners), loc="upper left", bbox_to_anchor=(0, -0.18),
              labelcolor=INK_2, handletextpad=0.3, columnspacing=1.2)
    path = out / "distinct_by_scenario.png"
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return path


def plot_paired(rows, out: Path, reference="abyss") -> Path:
    scenarios = _scenarios(rows)
    others = [p for p in _planners(rows) if p != reference]
    fig, ax = plt.subplots(figsize=(8, 1.1 * len(scenarios) + 1.4), facecolor=SURFACE)
    _style(ax)
    ax.axvline(0, color=INK_2, linewidth=1)
    offsets = np.linspace(-0.33, 0.33, len(others))
    for off, planner in zip(offsets, others):
        means, lows, highs = [], [], []
        for s in scenarios:
            ref, other = _values(rows, s, reference), _values(rows, s, planner)
            seeds = sorted(ref.keys() & other.keys())
            m, lo, hi = paired_ci(np.array([ref[k] - other[k] for k in seeds], float))
            means.append(m)
            lows.append(m - lo)
            highs.append(hi - m)
        y = np.arange(len(scenarios)) + off
        ax.errorbar(means, y, xerr=[lows, highs], fmt=MARKERS.get(planner, "o"), ms=7,
                    color=COLORS.get(planner, INK_2), ecolor=COLORS.get(planner, INK_2),
                    elinewidth=2, capsize=0, mec=SURFACE, mew=1.5, label=planner)
    ax.set_yticks(range(len(scenarios)), scenarios, color=INK)
    ax.invert_yaxis()
    ax.set_xlabel(f"{reference} minus planner, categories (paired, 95% bootstrap CI)  ·  "
                  f"right of 0 = {reference} found more", color=INK_2)
    ax.set_title(f"Paired advantage of {reference} on identical worlds", loc="left", color=INK)
    ax.legend(frameon=False, ncol=min(len(others), 6), loc="upper left",
              bbox_to_anchor=(0, -0.14), labelcolor=INK_2, handletextpad=0.3, columnspacing=1.2)
    path = out / "paired_difference.png"
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return path


def discovery_curves(config, scenario, planners, seeds, grid) -> dict[str, np.ndarray]:
    """Mean cumulative true distinct categories at each energy level in ``grid``."""
    config = replace(config, scenario=scenario)
    curves = {}
    for planner in planners:
        runs = []
        for seed in seeds:
            log, reveal = run_mission(config, PLANNERS[planner](), seed)
            surveys = [s for s in log["steps"] if s["observation"] is not None]
            energy = [s["cumulative"]["energy_used"] for s in surveys]
            seen, counts = set(), []
            for obs in reveal["true_observations"]:
                seen.update(obs["categories"])
                counts.append(len(seen))
            # Step function: count found by each energy level.
            idx = np.searchsorted(energy, grid, side="right")
            runs.append(np.where(idx > 0, np.array([0, *counts])[idx], 0))
        curves[planner] = np.mean(runs, axis=0)
    return curves


def plot_curves(config, out: Path, scenarios, planners, seeds) -> Path:
    grid = np.linspace(0, config.energy_budget, 151)
    fig, axes = plt.subplots(1, len(scenarios), figsize=(3.2 * len(scenarios), 3.4),
                             sharey=True, facecolor=SURFACE)
    axes = np.atleast_1d(axes)
    for ax, scenario in zip(axes, scenarios):
        _style(ax)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        for planner, curve in discovery_curves(config, scenario, planners, seeds, grid).items():
            ax.plot(grid, curve, color=COLORS.get(planner, INK_2), linewidth=2, label=planner)
        ax.set_title(scenario, loc="left", color=INK, fontsize=11)
        ax.set_xlabel("Energy spent", color=INK_2)
    axes[0].set_ylabel("True distinct categories (mean)", color=INK_2)
    fig.suptitle(f"Discoveries as the budget is spent ({len(seeds)} seeds per world)",
                 x=0.01, ha="left", color=INK)
    fig.tight_layout()
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, labelcolor=INK_2, ncol=len(labels),
               loc="upper left", bbox_to_anchor=(0.01, 0.0))
    path = out / "discovery_curves.png"
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", default="results/benchmark.csv")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--out", default="results/figures")
    ap.add_argument("--curve-seeds", type=int, default=10)
    ap.add_argument("--seed-offset", type=int, default=0, help="match the benchmark run")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = load_rows(a.csv)
    paths = [plot_distinct(rows, out), plot_paired(rows, out)]
    seeds = range(a.seed_offset, a.seed_offset + a.curve_seeds)
    main_planners = [p for p in _planners(rows) if not p.startswith("abyss-")]
    paths.append(plot_curves(load_config(a.config), out, _scenarios(rows), main_planners, seeds))
    for p in paths:
        print(f"wrote {p}")


if __name__ == "__main__":
    main()
