"""Extra demo landforms must be fixed, labelled and kept apart from the default worlds."""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from abyss.config import load_config
from abyss.landforms import LANDFORMS, landform_terrain
from abyss.planners import PLANNERS
from abyss.run_mission import run_mission, validate_mission_log


@pytest.mark.parametrize("name", LANDFORMS)
def test_landform_is_fixed_labelled_and_in_range(name):
    a = landform_terrain(name, (30, 30), 463.0)
    b = landform_terrain(name, (30, 30), 463.0)
    assert np.array_equal(a.depth_m, b.depth_m)
    assert a.source == f"synthetic_{name}"
    assert a.depth_m.min() >= 50.0
    assert np.ptp(a.depth_m) < 2200.0


def test_landforms_have_the_shapes_they_are_named_for():
    seamount = landform_terrain("seamount", (30, 30), 463.0).depth_m
    basin = landform_terrain("basin", (30, 30), 463.0).depth_m
    # A seamount's peak is far shallower than its edges; a basin's middle is deeper.
    assert seamount[16, 18] < np.median(seamount[0]) - 1000.0
    assert basin[16, 16] > np.median(basin[0]) + 600.0


def test_supplied_terrain_is_named_in_the_world_id_and_default_is_unchanged():
    config = replace(load_config("config.yaml"), scenario="ridge", rho=0.5)
    terrain = landform_terrain("trench", (config.height, config.width), config.cell_size_m)
    log, _ = run_mission(config, PLANNERS["abyss"](), 1000, terrain=terrain)
    validate_mission_log(log)
    assert log["world"]["id"] == "synthetic_trench-ridge-rho0.5-seed1000"
    assert log["provenance"]["terrain"] == "synthetic_trench"
    assert log["outcome"]["safe_return"]

    default, _ = run_mission(config, PLANNERS["abyss"](), 1000)
    assert default["world"]["id"] == "ridge-rho0.5-seed1000"


def test_demo_manifest_lists_landforms_after_the_real_terrain():
    entries = json.loads(Path("ui/logs/index.json").read_text(encoding="utf-8"))["entries"]
    assert entries[0]["world_id"] == "ridge-rho0.5-seed1000"
    landforms = {e["terrain"] for e in entries if e["terrain"].startswith("synthetic_")}
    assert landforms == {f"synthetic_{name}" for name in LANDFORMS}
    assert all(Path("ui", e["log"]).is_file() for e in entries)
