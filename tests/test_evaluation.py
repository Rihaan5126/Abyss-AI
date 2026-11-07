"""Benchmark, metrics, plots and the habitat-coverage option run end to end."""

from __future__ import annotations

import numpy as np

from abyss.config import SimConfig
from abyss.evaluation import plots
from abyss.evaluation.benchmark import paired_ci, run_benchmark, summarise
from abyss.planners.adaptive import AdaptivePlanner
from abyss.run_mission import run_mission, validate_mission_log


def test_benchmark_rows_and_summary():
    rows = run_benchmark(SimConfig(), ["ridge"], range(2), ("abyss", "frontier"))
    assert len(rows) == 4
    assert all(r["safe_return"] for r in rows)
    entries = summarise(rows)
    assert {e["planner"] for e in entries} == {"abyss", "frontier"}


def test_paired_ci_brackets_mean():
    mean, low, high = paired_ci(np.array([1.0, 2.0, 3.0, 4.0]))
    assert low <= mean <= high


def test_habitat_coverage_missions_are_safe():
    for mode in ("habitat", "both"):
        log, _ = run_mission(SimConfig(), AdaptivePlanner(), 0, planner_config={"coverage": mode})
        validate_mission_log(log)
        assert not log["outcome"]["forced_return"]


def test_plots_write_files(tmp_path):
    config = SimConfig()
    rows = run_benchmark(config, ["random"], range(2), ("abyss", "frontier"))
    for r in rows:
        r["distinct_categories"] = float(r["distinct_categories"])
    assert plots.plot_distinct(rows, tmp_path).exists()
    assert plots.plot_paired(rows, tmp_path).exists()
    assert plots.plot_curves(config, tmp_path, ["random"], ["abyss"], range(1)).exists()
