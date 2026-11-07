"""The adapter between Ammar's perception package and the simulator.

The fake encoder tests wiring and arithmetic, not computer-vision quality. Tests that
need the perception package are skipped when it isn't available.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from abyss.config import SimConfig
from abyss.fathomnet_perception import (
    FathomNetImagePool,
    FathomNetPerception,
    build_kit,
    read_test_rows,
)
from abyss.planners import RandomPlanner
from abyss.run_mission import run_mission, validate_mission_log, write_logs

COLOURS = {"jelly": (220, 10, 10), "squid": (10, 220, 10), "ghostfish": (10, 10, 220)}
FAMILIAR = ["jelly", "squid"]
CONFIG = SimConfig(
    perception_mode="real", n_categories=3, prevalence_max=0.5, prevalence_min=0.2, energy_budget=150.0
)


class FakeEncoder:
    identity = "test/only-encoder:v1"

    def encode(self, images):
        return np.array(
            [np.asarray(Image.open(i).convert("RGB"))[0, 0].astype(float) + 1 for i in images]
        )


def write_manifest(root: Path) -> Path:
    rows = []
    for category, colour in COLOURS.items():
        counts = {"test": 4}
        if category in FAMILIAR:
            counts |= {"reference": 6, "validation": 4}
        for split, count in counts.items():
            for index in range(count):
                name = f"{category}-{split}-{index}"
                path = root / "crops" / f"{name}.png"
                path.parent.mkdir(exist_ok=True)
                shade = tuple(min(255, c + index * 3) for c in colour)
                Image.new("RGB", (8, 8), shade).save(path)
                rows.append(
                    {
                        "sample_id": name,
                        "category": category,
                        "image_path": f"crops/{name}.png",
                        "source_id": f"dive-{category}-{split}",
                        "split": split,
                    }
                )
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps(rows), encoding="utf-8")
    return manifest


@pytest.fixture
def manifest(tmp_path):
    return write_manifest(tmp_path)


@pytest.fixture
def real_kit(manifest):
    pytest.importorskip("perception")
    from perception.dataset import read_manifest
    from perception.evaluate import fit_perception

    model = fit_perception(read_manifest(manifest), FAMILIAR, FakeEncoder())
    return build_kit(model, manifest)


def test_pool_uses_only_test_images(manifest):
    rows = read_test_rows(manifest)
    assert {row["split"] for row in rows} == {"test"}
    pool = FathomNetImagePool(rows, FAMILIAR)
    assert pool.categories == ("jelly", "squid", "ghostfish")
    assert pool.withheld == ("ghostfish",)
    assert all(not {"reference", "validation"} & set(Path(p).stem.split("-")) for p in pool.image_paths)


def test_refs_are_opaque_and_load_the_image(manifest):
    pool = FathomNetImagePool(read_test_rows(manifest), FAMILIAR)
    for category in pool.categories:
        for ref in pool.images_for(category):
            assert ref.startswith("img://")
            assert category not in ref and "crops" not in ref
            assert Path(pool.load(ref)).exists()


def test_manifest_without_splits_is_refused(tmp_path):
    path = tmp_path / "unsplit.json"
    path.write_text(json.dumps([{"sample_id": "a", "category": "jelly", "image_path": "a.png"}]))
    with pytest.raises(ValueError, match="no splits"):
        read_test_rows(path)


def test_familiar_category_without_test_images_is_refused(manifest):
    rows = [r for r in read_test_rows(manifest) if r["category"] != "squid"]
    with pytest.raises(ValueError, match="squid"):
        FathomNetImagePool(rows, FAMILIAR)


def test_adapter_maps_field_names():
    upstream = SimpleNamespace(
        predicted_category="jelly", similarity_score=0.9, novelty_score=0.1, is_unknown=False
    )
    model = SimpleNamespace(encoder=SimpleNamespace(identity="enc"), predict=lambda image: upstream)
    adapter = FathomNetPerception(model)
    result = adapter.predict("a.png")
    assert adapter.name == "enc"
    assert (result.predicted_category, result.similarity, result.novelty_score) == ("jelly", 0.9, 0.1)
    assert result.is_unknown is False and result.image_ref == "a.png"


def test_references_in_the_pool_are_refused(manifest):
    pool_paths = read_test_rows(manifest)
    model = SimpleNamespace(
        encoder=SimpleNamespace(identity="enc"),
        index=SimpleNamespace(labels=FAMILIAR, references=[pool_paths[0]["image_path"]]),
    )
    with pytest.raises(ValueError, match="also model references"):
        build_kit(model, manifest)


def test_real_classes_recognise_familiar_and_flag_withheld(real_kit):
    perception, pool = real_kit["perception"], real_kit["image_pool"]
    for category in FAMILIAR:
        for ref in pool.images_for(category):
            assert perception.predict(pool.load(ref)).predicted_category == category
    for ref in pool.images_for("ghostfish"):
        result = perception.predict(pool.load(ref))
        assert result.is_unknown and result.predicted_category is None


def test_real_classes_run_a_full_mission_without_leaks(real_kit, manifest, tmp_path):
    log, reveal = run_mission(CONFIG, RandomPlanner(), 0, **real_kit)
    validate_mission_log(log)
    text = json.dumps(log)
    assert log["provenance"]["perception"] == FakeEncoder.identity
    assert str(manifest.parent) not in text and "crops" not in text
    assert "ghostfish" not in text  # withheld categories can't be named by the model
    assert "true_category" not in text
    assert log["outcome"]["unknown_encounters"] > 0
    assert reveal["perception_summary"]["unknown_recall"] == 1

    log_path, reveal_path = write_logs(log, reveal, tmp_path / "out")
    assert log_path.exists() and reveal_path.exists()
    assert ":" not in log_path.name and "/" not in log_path.name
