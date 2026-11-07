"""The ideal vs real comparison measures vision errors and nothing else."""

import json
from dataclasses import replace

import pytest
from test_fathomnet_perception import FAMILIAR, FakeEncoder, write_manifest

from abyss.config import SimConfig
from abyss.contract import PerceptionResult
from abyss.evaluation.perception_compare import compare
from abyss.fathomnet_perception import build_kit
from abyss.stub_perception import StubImagePool, StubPerception

GEBCO = SimConfig(terrain_source="gebco")
SEEDS = (1000, 1001, 1002)
WORLDS = (("ridge", 0.5),)


class PerfectPerception:
    name = "perfect"

    def predict(self, image):
        return PerceptionResult(image.true_category, 1.0, 0.0, False, image.ref)


def _kit(perception_type, **kwargs):
    pool = StubImagePool(GEBCO.n_categories, n_withheld=0)
    if perception_type is StubPerception:
        return {"perception": StubPerception(pool, **kwargs), "image_pool": pool}
    return {"perception": perception_type(), "image_pool": pool}


def test_perfect_perception_matches_ideal_exactly():
    summary = compare(GEBCO, _kit(PerfectPerception), SEEDS, WORLDS)
    for row in summary["results"]:
        assert row["ideal_mean"] == row["real_mean"]
        assert row["real_minus_ideal"] == 0
        assert row["images_shown"]["correct"] == row["images_shown"]["images"]


def test_vision_errors_change_the_adaptive_planner_only_through_observations():
    kit = _kit(StubPerception, confusion_rate=0.6, false_alert_rate=0.2)
    summary = compare(GEBCO, kit, SEEDS, WORLDS)
    by_planner = {row["planner"]: row for row in summary["results"]}
    # Frontier ignores biology, so it surveys the same cells and its true score can't change.
    assert by_planner["frontier"]["real_minus_ideal"] == 0
    assert by_planner["abyss"]["images_shown"]["correct"] < by_planner["abyss"]["images_shown"]["familiar"]
    assert summary["safety"]["safe_returns"] == summary["safety"]["missions"]


def test_summary_is_json_ready_and_keeps_provenance():
    summary = compare(GEBCO, _kit(PerfectPerception), SEEDS[:1], WORLDS, ("frontier",))
    assert json.loads(json.dumps(summary))["provenance"]["biology"] == "simulated"
    assert summary["provenance"]["perception_model"] == "perfect"


def test_runs_through_the_real_perception_classes(tmp_path):
    pytest.importorskip("perception")
    from perception.dataset import read_manifest
    from perception.evaluate import fit_perception

    manifest = write_manifest(tmp_path)
    model = fit_perception(read_manifest(manifest), FAMILIAR, FakeEncoder())
    config = replace(GEBCO, prevalence_max=0.5, prevalence_min=0.2)
    summary = compare(config, build_kit(model, manifest), SEEDS[:2], WORLDS)
    assert summary["n_categories"] == 3
    assert summary["provenance"]["perception_model"] == FakeEncoder.identity
    assert sum(r["images_shown"]["flagged"] for r in summary["results"]) > 0
