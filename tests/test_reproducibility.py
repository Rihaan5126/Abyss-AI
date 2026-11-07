"""Same seeds give the same mission, and all planners share one world."""

import json

import numpy as np
import pytest
from helpers import ALL_SCENARIOS, FarthestPlanner

from abyss.config import SimConfig
from abyss.env import Environment
from abyss.planners import RandomPlanner
from abyss.run_mission import planner_seed_for, run_mission


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_identical_inputs_give_identical_logs(scenario):
    config = SimConfig(scenario=scenario)
    first = run_mission(config, RandomPlanner(), 7)
    second = run_mission(config, RandomPlanner(), 7)
    assert json.dumps(first) == json.dumps(second)


def test_different_seeds_give_different_worlds():
    first, second = Environment(SimConfig()), Environment(SimConfig())
    first.reset(1)
    second.reset(2)
    assert not np.array_equal(first._world.encounters, second._world.encounters)


def test_different_planner_seeds_change_the_route_not_the_world():
    config = SimConfig()
    log_a, reveal_a = run_mission(config, RandomPlanner(), 0, planner_seed=1)
    log_b, reveal_b = run_mission(config, RandomPlanner(), 0, planner_seed=2)
    assert log_a["steps"] != log_b["steps"]
    assert reveal_a["encounter_richness_map"] == reveal_b["encounter_richness_map"]


def test_same_waypoint_gives_same_observation_for_every_planner():
    config = SimConfig()
    reveals = [
        run_mission(config, RandomPlanner(), 4)[1],
        run_mission(config, FarthestPlanner(), 4)[1],
    ]
    assert reveals[0]["encounter_richness_map"] == reveals[1]["encounter_richness_map"]

    env_a, env_b = Environment(config), Environment(config)
    env_a.reset(4)
    env_b.reset(4)
    env_b.step((8, 8))  # a different history must not change what (5, 5) holds
    obs_a = env_a.step((5, 5)).observation
    obs_b = env_b.step((5, 5)).observation
    assert obs_a.categories == obs_b.categories
    assert obs_a.features == obs_b.features


def test_planner_randomness_is_independent_of_the_world_stream():
    assert planner_seed_for(0) != 0
    assert planner_seed_for(0) != planner_seed_for(1)
