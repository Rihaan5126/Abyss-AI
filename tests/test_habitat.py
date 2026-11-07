"""Habitat classes are public, deterministic and display-only."""

import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest
from helpers import ALL_SCENARIOS

from abyss.config import SimConfig
from abyss.contract import PublicMap, PublicState
from abyss.env import Environment
from abyss.habitat import N_CLASSES, habitat_classes
from abyss.planners import PLANNERS
from abyss.run_mission import run_mission, validate_mission_log

GEBCO = {"terrain_source": "gebco"}


def _public_map(**config):
    env = Environment(SimConfig(**config))
    env.reset(0)
    return env.public_map


def test_every_cell_gets_one_of_the_named_classes():
    habitat = habitat_classes(_public_map(**GEBCO))
    classes = np.array(habitat["classes"])
    assert classes.shape == (30, 30)
    assert set(np.unique(classes)) == set(range(N_CLASSES))
    assert len(set(habitat["names"])) == N_CLASSES


def test_classes_are_numbered_shallow_to_deep():
    public_map = _public_map(**GEBCO)
    classes = np.array(habitat_classes(public_map)["classes"])
    means = [public_map.depth_m[classes == k].mean() for k in range(N_CLASSES)]
    assert means == sorted(means)


def test_classes_depend_only_on_public_terrain():
    logs = [
        run_mission(SimConfig(scenario=scenario, **GEBCO), PLANNERS["frontier"](), seed)[0]
        for scenario, seed in (("ridge", 0), ("reversed", 0), ("random", 7))
    ]
    assert all(log["terrain"]["habitat"] == logs[0]["terrain"]["habitat"] for log in logs)


def test_planners_do_not_receive_habitat_data():
    names = {f.name for t in (PublicMap, PublicState) for f in dataclasses.fields(t)}
    assert not {n for n in names if "habitat" in n}


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_new_class_events_are_accurate(scenario):
    log, _ = run_mission(SimConfig(scenario=scenario, **GEBCO), PLANNERS["abyss"](), 1000)
    validate_mission_log(log)
    seen = set()
    classes = log["terrain"]["habitat"]["classes"]
    surveys = [s["observation"] for s in log["steps"] if s["observation"]]
    for observation in surveys:
        row, col = observation["waypoint"]
        habitat = observation["habitat"]
        assert habitat["class"] == classes[row][col]
        assert habitat["new_class"] == (habitat["class"] not in seen)
        seen.add(habitat["class"])
        assert habitat["classes_sampled"] == len(seen)
    assert surveys[0]["habitat"]["distance_to_sampled"] is None


def test_repeat_surveys_are_never_new():
    from helpers import RepeatPlanner

    log, _ = run_mission(SimConfig(**GEBCO), RepeatPlanner((3, 3)), 0)
    flags = [s["observation"]["habitat"]["new_class"] for s in log["steps"] if s["observation"]]
    assert flags[0] and not any(flags[1:])


def test_logs_are_identical_on_repeat_runs():
    first = run_mission(SimConfig(**GEBCO), PLANNERS["abyss"](), 1000)
    second = run_mission(SimConfig(**GEBCO), PLANNERS["abyss"](), 1000)
    assert json.dumps(first) == json.dumps(second)


def test_ui_logs_carry_habitat_data():
    manifest = json.loads(Path("ui/logs/index.json").read_text(encoding="utf-8"))
    log = json.loads(Path("ui", manifest["entries"][0]["log"]).read_text(encoding="utf-8"))
    assert "not biomes" in log["terrain"]["habitat"]["note"].lower()
