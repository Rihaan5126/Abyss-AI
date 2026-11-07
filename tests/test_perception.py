"""Scientific boundary tests; a deterministic fake encoder tests math, not CV quality."""

import json

import numpy as np
from PIL import Image
import pytest

from perception.dataset import make_splits, validate_splits
from perception.embed import CachedEncoder
from perception.evaluate import evaluate, fit_perception
from perception.novelty import ReferenceIndex, calibrate_threshold
from perception.perception import Perception
from perception.preprocess import crop_organism, dinov2_pixels


class FakeEncoder:
    identity = "test-only-encoder"

    def __init__(self):
        self.calls = 0

    def encode(self, images):
        self.calls += 1
        return np.array([np.asarray(image)[0, 0, :].astype(float) + 1 for image in images])


def manifest():
    rows = []
    for group in range(12):
        for category in ("jelly", "squid", "withheld"):
            rows.append({"sample_id": f"{group}-{category}", "category": category,
                         "source_id": f"dive-{group}", "image_path": f"{group}-{category}.png",
                         "image_uuid": f"image-{group}-{category}"})
    return rows


def test_splits_reproducible_source_disjoint_and_unknowns_excluded():
    rows = make_splits(manifest(), ["jelly", "squid"])
    assert rows == make_splits(manifest(), ["jelly", "squid"])
    validate_splits(rows, ["jelly", "squid"])
    assert all(r["split"] == "test" for r in rows if r["category"] == "withheld")
    for group in {r["source_id"] for r in rows}:
        assert len({r["split"] for r in rows if r["source_id"] == group}) == 1


@pytest.mark.parametrize("field", ["source_id", "image_uuid", "original_sha256", "crop_sha256", "image_path"])
def test_split_validator_rejects_leakage(field):
    rows = make_splits(manifest(), ["jelly", "squid"])
    a = next(r for r in rows if r["split"] == "reference")
    b = next(r for r in rows if r["split"] == "test")
    a[field] = b[field] = "same-original"
    with pytest.raises(ValueError, match="Leakage"):
        validate_splits(rows, ["jelly", "squid"])


def test_duplicate_originals_merge_sources_before_splitting():
    source_rows = manifest()
    source_rows[0]["original_sha256"] = source_rows[3]["original_sha256"] = "duplicate"
    rows = make_splits(source_rows, ["jelly", "squid"])
    assert len({r["split"] for r in rows if r["source_id"] in {"dive-0", "dive-1"}}) == 1


def test_refuses_to_fall_back_to_leaking_image_split():
    rows = manifest()
    for row in rows:
        row["source_id"] = "single-dive"
    with pytest.raises(ValueError, match="three independent"):
        make_splits(rows, ["jelly", "squid"])


def test_cosine_novelty_calibration_and_threshold_ties():
    index = ReferenceIndex(np.array([[1, 0], [0, 1]]), ["jelly", "squid"], ["a", "b"])
    distances, indices = index.query(np.array([[2, 0], [0, -1]]))
    np.testing.assert_allclose(distances, [0, 1])
    assert indices[0] == 0
    threshold = calibrate_threshold(np.array([0, .1, .2, .3]), .25)
    assert threshold == .3
    with pytest.raises(ValueError):
        ReferenceIndex(np.zeros((1, 2)), ["a"], ["b"])


def test_image_only_prediction_save_reload_and_encoder_mismatch(tmp_path):
    encoder = FakeEncoder()
    image = Image.new("RGB", (10, 10), "red")
    index = ReferenceIndex(encoder.encode([image]), ["jelly"], ["reference.png"])
    perception = Perception(encoder, index, .01)
    result = perception.predict(image)
    assert result.predicted_category == "jelly" and not result.is_unknown
    assert result.image_reference is None
    assert "true_category" not in result.to_dict()
    unknown = perception.predict(Image.new("RGB", (10, 10), "green"))
    assert unknown.is_unknown and unknown.predicted_category is None
    perception.save(tmp_path)
    loaded = Perception.load(tmp_path, encoder)
    assert loaded.predict(image) == result
    encoder.identity = "different-weights"
    with pytest.raises(ValueError, match="different encoder"):
        Perception.load(tmp_path, encoder)


def test_embedding_cache_uses_pixels_and_encoder_identity(tmp_path):
    encoder = FakeEncoder()
    cache = CachedEncoder(encoder, tmp_path)
    image = Image.new("RGB", (3, 3), "red")
    first = cache.encode([image])
    np.testing.assert_array_equal(first, cache.encode([image.copy()]))
    assert encoder.calls == 1
    image.putpixel((0, 0), (1, 2, 3))
    cache.encode([image])
    encoder.identity = "other-model"
    cache.encode([image])
    assert encoder.calls == 3


def test_crops_clip_bounds_and_reject_empty():
    image = Image.new("RGB", (20, 10), "blue")
    assert crop_organism(image, dict(x=-2, y=2, width=5, height=20)).size == (3, 8)
    for box in [dict(x=50, y=0, width=2, height=2), dict(x=0, y=0, width=-2, height=2),
                dict(x=float("nan"), y=0, width=2, height=2)]:
        with pytest.raises(ValueError):
            crop_organism(image, box)
    assert dinov2_pixels(image).shape == (3, 224, 224)


def test_embedding_cache_accounts_for_exif_orientation(tmp_path):
    encoder = FakeEncoder()
    cache = CachedEncoder(encoder, tmp_path)
    ordinary = Image.new("RGB", (20, 10), "blue")
    rotated = ordinary.copy()
    rotated.getexif()[274] = 6
    cache.encode([ordinary, rotated])
    assert encoder.calls == 2


def test_heldout_images_cannot_change_fitted_references_or_threshold(tmp_path):
    rows = make_splits(manifest(), ["jelly", "squid"])
    images = {}
    for row in rows:
        rgb = {"jelly": "red", "squid": "blue", "withheld": "green"}[row["category"]]
        images[row["image_path"]] = Image.new("RGB", (3, 3), rgb)

    class PathEncoder(FakeEncoder):
        def encode(self, paths):
            return super().encode([images[path] for path in paths])

    encoder = PathEncoder()
    first = fit_perception(rows, ["jelly", "squid"], encoder)
    for row in rows:
        if row["split"] == "test":
            images[row["image_path"]] = Image.new("RGB", (3, 3), "white")
    second = fit_perception(rows, ["jelly", "squid"], encoder)
    assert first.threshold == second.threshold
    np.testing.assert_array_equal(first.index.embeddings, second.index.embeddings)
    report = evaluate(second, rows, ["jelly", "squid"])
    json.dumps(report, allow_nan=False)
    assert report["counts"]["test_unknown"] > 0
