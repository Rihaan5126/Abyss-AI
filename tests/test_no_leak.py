"""Planners must only receive what a real robot could know."""

import dataclasses
import json

import numpy as np
import pytest
from helpers import ALL_SCENARIOS

from abyss.config import SimConfig
from abyss.contract import PublicMap, PublicState
from abyss.env import Environment
from abyss.planners import RandomPlanner
from abyss.planners.base import Planner
from abyss.run_mission import run_mission
from abyss.world import HiddenWorld


def _public_arrays(obj):
    for field in dataclasses.fields(obj):
        value = getattr(obj, field.name)
        if isinstance(value, np.ndarray):
            yield field.name, value


def _assert_no_hidden_objects(obj):
    for field in dataclasses.fields(obj):
        value = getattr(obj, field.name)
        assert not isinstance(value, (HiddenWorld, Environment)), field.name
        assert "scenario" not in field.name and "rho" != field.name


def _assert_public_equal(first, second):
    for field in dataclasses.fields(first):
        a, b = getattr(first, field.name), getattr(second, field.name)
        if isinstance(a, np.ndarray):
            assert np.array_equal(a, b), field.name
        else:
            assert a == b, field.name


def test_public_objects_hold_no_hidden_data():
    env = Environment(SimConfig())
    state = env.reset(0)
    _assert_no_hidden_objects(state)
    _assert_no_hidden_objects(env.public_map)
    hidden = (env._world.probability, env._world.encounters)
    for obj in (state, env.public_map):
        for name, array in _public_arrays(obj):
            for secret in hidden:
                assert array.shape != secret.shape, name


@pytest.mark.parametrize("scenario", ALL_SCENARIOS[1:])
def test_initial_public_view_does_not_depend_on_hidden_world(scenario):
    base = Environment(SimConfig(scenario=ALL_SCENARIOS[0]))
    other = Environment(SimConfig(scenario=scenario))
    state_a, state_b = base.reset(5), other.reset(5)
    _assert_public_equal(state_a, state_b)
    _assert_public_equal(base.public_map, other.public_map)


def test_observation_blind_planner_moves_identically_in_every_world():
    routes = []
    for scenario in ALL_SCENARIOS:
        log, _ = run_mission(SimConfig(scenario=scenario), RandomPlanner(), 3)
        routes.append([step["route"] for step in log["steps"]])
    assert all(route == routes[0] for route in routes)


def test_public_arrays_cannot_be_modified():
    env = Environment(SimConfig())
    state = env.reset(0)
    for obj in (state, env.public_map):
        for name, array in _public_arrays(obj):
            with pytest.raises(ValueError):
                array.flat[0] = array.flat[0]


def test_planner_only_receives_public_types():
    seen = []

    class Spy(RandomPlanner):
        name = "spy"

        def reset(self, public_map, config, seed):
            seen.extend([public_map, config])
            super().reset(public_map, config, seed)

        def choose_target(self, public_state, observation_history):
            seen.append(public_state)
            return super().choose_target(public_state, observation_history)

    run_mission(SimConfig(), Spy(), 0)
    assert isinstance(seen[0], PublicMap)
    assert seen[1] == {}
    assert all(isinstance(item, PublicState) for item in seen[2:])
    assert issubclass(Spy, Planner)


def test_mission_log_excludes_hidden_maps():
    log, reveal = run_mission(SimConfig(), RandomPlanner(), 0)
    text = json.dumps(log)
    for key in ("probability", "encounters", "expected_richness_map", "encounter_richness_map"):
        assert key not in text
    assert "expected_richness_map" in reveal
    assert reveal["biology_provenance"] == "simulated"
