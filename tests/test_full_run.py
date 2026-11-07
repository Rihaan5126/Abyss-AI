"""The full benchmark is honest: frozen settings, separate seeds and a complete record."""

import json
from pathlib import Path

import pytest

from abyss.config import SimConfig
from abyss.evaluation.benchmark import DEFAULT_PLANNERS, run_benchmark
from abyss.evaluation.full_run import EVALUATION_SEEDS, OTHERS, TERRAINS, WORLDS, summarise_all
from abyss.evaluation.report import render
from abyss.planners.adaptive import DEFAULTS

COMMITTED = Path("ui/logs/benchmark.json")


@pytest.fixture(scope="module")
def committed():
    return json.loads(COMMITTED.read_text(encoding="utf-8"))


def test_evaluation_seeds_follow_the_seed_policy():
    assert min(EVALUATION_SEEDS) >= 1000


def test_small_run_summarises_every_planner():
    rows = [
        {"terrain": "gebco", **row}
        for row in run_benchmark(SimConfig(terrain_source="gebco"), ["ridge"], (1000, 1001, 1002), DEFAULT_PLANNERS, 0.5)
    ]
    summary = summarise_all(rows, (1000, 1001, 1002), SimConfig().to_dict())
    world = summary["worlds"][0]
    assert set(world["planners"]) == set(DEFAULT_PLANNERS)
    assert set(world["abyss_vs"]) == set(OTHERS)
    comparison = world["abyss_vs"]["frontier"]
    assert comparison["wins"] + comparison["ties"] + comparison["losses"] == 3
    assert summary["safety"]["safe_returns"] == summary["safety"]["missions"] == len(rows)


def test_committed_results_are_complete_and_safe(committed):
    assert committed["seeds"] == list(EVALUATION_SEEDS)
    safety = committed["safety"]
    assert safety["safe_returns"] == safety["missions"]
    assert safety["forced_returns"] == 0
    expected = len(DEFAULT_PLANNERS) * len(WORLDS) * len(TERRAINS) * len(EVALUATION_SEEDS)
    assert safety["missions"] == expected
    assert committed["provenance"]["biology"] == "simulated"


def test_committed_results_use_the_frozen_weights(committed):
    frozen = committed["frozen_config"]["abyss"]
    assert frozen["beta"] == DEFAULTS["beta"] and frozen["gamma"] == DEFAULTS["gamma"]


def test_results_document_matches_the_committed_benchmark(committed):
    assert Path("docs/results.md").read_text(encoding="utf-8") == render(committed)
