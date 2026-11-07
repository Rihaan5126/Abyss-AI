"""The committed GEBCO crop loads and runs under the same rules as synthetic terrain."""

import json

import numpy as np
import pytest
from helpers import ALL_SCENARIOS

from abyss.config import SimConfig
from abyss.env import Environment
from abyss.planners import RandomPlanner
from abyss.run_mission import run_mission, validate_mission_log
from abyss.terrain import terrain_from_depth

GEBCO = {"terrain_source": "gebco"}


def test_crop_is_all_ocean_with_attribution():
    crop = json.loads(open(SimConfig().gebco_path, encoding="utf-8").read())
    assert np.array(crop["elevation_m"]).shape == (30, 30)
    assert np.array(crop["elevation_m"]).max() < 0
    assert "doi:10.5285" in crop["citation"]


def test_public_terrain_is_positive_down_and_fixed_across_seeds():
    first, second = Environment(SimConfig(**GEBCO)), Environment(SimConfig(**GEBCO))
    first.reset(0)
    second.reset(1)
    assert first.public_map.terrain_source == "gebco_2025"
    assert (first.public_map.depth_m > 0).all()
    assert np.array_equal(first.public_map.depth_m, second.public_map.depth_m)
    assert not np.array_equal(first._world.encounters, second._world.encounters)


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_missions_are_safe_on_gebco(scenario):
    log, reveal = run_mission(SimConfig(scenario=scenario, **GEBCO), RandomPlanner(), 0)
    validate_mission_log(log)
    assert log["provenance"] == {
        "terrain": "gebco_2025",
        "biology": "simulated",
        "perception": "ideal",
    }
    assert reveal["biology_provenance"] == "simulated"


def test_slope_uses_separate_cell_spacing():
    # A 1 m per column ramp is twice as steep when columns are half as wide.
    depth = np.tile(np.arange(30.0), (30, 1))
    square = terrain_from_depth(depth, 100.0, "test").slope_deg
    narrow = terrain_from_depth(depth, 100.0, "test", 50.0).slope_deg
    assert np.tan(np.radians(narrow[15, 15])) == pytest.approx(
        2 * np.tan(np.radians(square[15, 15]))
    )


def test_wrong_grid_size_is_refused():
    with pytest.raises(ValueError, match="GEBCO crop"):
        Environment(SimConfig(height=20, width=20, **GEBCO)).reset(0)
