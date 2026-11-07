"""The experimental planner learns the discovery rate and leaves the official planner alone."""

import json
from pathlib import Path

import pytest
from helpers import ALL_SCENARIOS

from abyss.config import SimConfig
from abyss.contract import Observation
from abyss.env import Environment
from abyss.evaluation.benchmark import DEFAULT_PLANNERS
from abyss.evaluation.novelty_experiment import DEVELOPMENT_SEEDS, FRESH_SEEDS, render
from abyss.planners import PLANNERS
from abyss.planners.adaptive import DEFAULTS
from abyss.planners.novelty import NoveltyPlanner
from abyss.run_mission import run_mission, validate_mission_log


def _planner(**config):
    env = Environment(SimConfig(terrain_source="gebco"))
    env.reset(0)
    planner = NoveltyPlanner()
    planner.reset(env.public_map, config, 0)
    return planner, env


def _obs(env, cell, categories, unknown=()):
    features = tuple(float(v) for v in env.public_map.features[cell])
    return Observation(1, cell, env.public_map.feature_names, features, tuple(categories), 2.0, unknown_flags=tuple(unknown))


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_missions_are_safe(scenario):
    log, _ = run_mission(SimConfig(scenario=scenario, terrain_source="gebco"), NoveltyPlanner(), 0)
    validate_mission_log(log)
    assert log["outcome"]["safe_return"] and not log["outcome"]["forced_return"]


def test_known_categories_stop_counting_as_discoveries():
    planner, env = _planner()
    planner.observe(_obs(env, (3, 3), ["a", "b"]))
    planner.observe(_obs(env, (3, 4), ["a", "b"]))
    assert planner._targets == [2.0, 0.0]


def test_rich_habitat_loses_value_once_it_stops_yielding_new_categories():
    planner, env = _planner()
    cell = (3, 3)
    planner.observe(_obs(env, cell, ["a", "b", "c"]))
    before = planner.belief()[0][cell]
    for _ in range(6):
        planner.observe(_obs(env, cell, ["a", "b", "c"]))
    assert planner.belief()[0][cell] < before


def test_forgetting_makes_recent_surveys_count_for_more():
    remembering, env = _planner(forgetting=1.0)
    forgetting, _ = _planner(forgetting=0.6)
    for planner in (remembering, forgetting):
        planner.observe(_obs(env, (3, 3), ["a", "b", "c", "d"]))
        for _ in range(4):
            planner.observe(_obs(env, (3, 3), ["a"]))
    assert forgetting.belief()[0][3, 3] < remembering.belief()[0][3, 3]


def test_unfamiliar_images_count_as_novel():
    planner, env = _planner()
    planner.observe(_obs(env, (3, 3), [], unknown=(True, True)))
    assert planner._targets == [2.0]


def test_no_new_information_about_hidden_world_is_used():
    # With an observation-blind target, routes in two worlds can differ only through surveys.
    routes = [
        [s["route"] for s in run_mission(SimConfig(scenario=w, terrain_source="gebco"), NoveltyPlanner(), 2)[0]["steps"]]
        for w in ("ridge", "reversed")
    ]
    assert routes[0][0] == routes[1][0]


def test_official_planner_set_and_weights_are_untouched():
    assert "abyss-novelty" not in DEFAULT_PLANNERS
    assert "abyss-novelty" in PLANNERS
    assert (DEFAULTS["beta"], DEFAULTS["gamma"]) == (1.0, 0.5)


def test_document_matches_the_recorded_experiment():
    data = json.loads(Path("docs/novelty-experiment.json").read_text(encoding="utf-8"))
    assert Path("docs/novelty-experiment.md").read_text(encoding="utf-8") == render(data)
    assert data["safety"]["missions"] == data["safety"]["safe_returns"]
    assert data["seeds"] == list(FRESH_SEEDS)


def test_tuning_and_final_seeds_are_separate_from_each_other_and_the_official_run():
    assert max(DEVELOPMENT_SEEDS) < 1000
    assert min(FRESH_SEEDS) >= 2000
