"""The replay UI's logs are real, valid and keep hidden truth in separate files."""

import json
from pathlib import Path

import pytest

from abyss.run_mission import validate_mission_log
from scripts.build_ui_logs import build

UI_ROOT = Path("ui")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("logs")
    return out, build("config.yaml", out, seed=0)


def test_each_world_has_a_side_by_side_pair(built):
    _, manifest = built
    worlds = {}
    for entry in manifest["entries"]:
        worlds.setdefault(entry["world_id"], []).append(entry)
    assert len(worlds) == 5
    assert all(entries[1]["planner"] == "abyss" for entries in worlds.values())
    assert all(len(entries) >= 2 for entries in worlds.values())


def test_built_logs_are_valid_and_public(built):
    out, manifest = built
    for entry in manifest["entries"]:
        text = (out / Path(entry["log"]).name).read_text(encoding="utf-8")
        validate_mission_log(json.loads(text))
        assert "expected_richness_map" not in text
        reveal = json.loads((out / Path(entry["reveal"]).name).read_text(encoding="utf-8"))
        assert "expected_richness_map" in reveal


def test_committed_logs_are_valid_and_public():
    manifest = json.loads((UI_ROOT / "logs" / "index.json").read_text(encoding="utf-8"))
    for entry in manifest["entries"]:
        text = (UI_ROOT / entry["log"]).read_text(encoding="utf-8")
        validate_mission_log(json.loads(text))
        assert "expected_richness_map" not in text
        assert (UI_ROOT / entry["reveal"]).exists()


def test_extra_oceans_move_the_organisms(tmp_path):
    """Each extra ocean is a new seed: same terrain, organisms in different places."""
    manifest = build("config.yaml", tmp_path, seed=0, oceans=3)
    ridge = [e for e in manifest["entries"] if e["scenario"] == "ridge"]
    assert sorted({e["seed"] for e in ridge}) == [0, 1, 2]
    for seed in (1, 2):
        planners = {e["planner"] for e in ridge if e["seed"] == seed}
        assert {"abyss", "frontier"} <= planners
    maps = []
    for seed in (0, 1):
        entry = next(e for e in ridge if e["seed"] == seed and e["planner"] == "abyss")
        reveal = json.loads((tmp_path / Path(entry["reveal"]).name).read_text())
        maps.append(reveal["encounter_richness_map"])
    assert maps[0] != maps[1]
