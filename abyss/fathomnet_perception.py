"""Connect Ammar's ``perception`` package to the simulator's interfaces.

Only held-out test images enter the pool, so the model never sees its own reference or
calibration images during a mission. Planners only get opaque image refs: real paths
hold local folder names, and the manifest that maps refs to labels stays private here.

The images are simulated camera encounters, not sightings at these coordinates.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .contract import PerceptionResult


def read_test_rows(manifest_path: str | Path) -> list[dict]:
    """Return test-split rows from a manifest, with absolute image paths."""
    path = Path(manifest_path).resolve()
    rows = json.loads(path.read_text(encoding="utf-8"))
    if any("split" not in row for row in rows):
        raise ValueError("Manifest has no splits. Use the split manifest from perception.")
    return [
        {**row, "image_path": str((path.parent / row["image_path"]).resolve())}
        for row in rows
        if row["split"] == "test"
    ]


class FathomNetImagePool:
    """Held-out images by category. Familiar categories come first, so withheld ones are rarest."""

    def __init__(self, rows: list[dict], familiar: list[str]) -> None:
        present = {row["category"] for row in rows}
        missing = set(familiar) - present
        if missing:
            raise ValueError(f"No test images for familiar categories: {sorted(missing)}")
        self.withheld = tuple(sorted(present - set(familiar)))
        self.categories = tuple(sorted(familiar)) + self.withheld
        self._paths: dict[str, str] = {}
        self._refs: dict[str, list[str]] = {category: [] for category in self.categories}
        for row in sorted(rows, key=lambda r: r["sample_id"]):
            digest = hashlib.sha256(row["sample_id"].encode()).hexdigest()[:16]
            ref = f"img://{digest}"
            self._paths[ref] = row["image_path"]
            self._refs[row["category"]].append(ref)

    def images_for(self, category: str) -> tuple[str, ...]:
        return tuple(self._refs[category])

    def load(self, ref: str) -> str:
        return self._paths[ref]

    @property
    def image_paths(self) -> set[str]:
        return set(self._paths.values())


class FathomNetPerception:
    """Adapts a fitted ``perception.Perception`` to the simulator's contract."""

    def __init__(self, model) -> None:
        self._model = model
        self.name = model.encoder.identity

    def predict(self, image: str) -> PerceptionResult:
        result = self._model.predict(image)
        return PerceptionResult(
            predicted_category=result.predicted_category,
            similarity=result.similarity_score,
            novelty_score=result.novelty_score,
            is_unknown=result.is_unknown,
            image_ref=str(image),
        )


def build_kit(model, manifest_path: str | Path) -> dict:
    """Pair a fitted model with its test images, as keyword arguments for ``run_mission``."""
    pool = FathomNetImagePool(read_test_rows(manifest_path), sorted(set(model.index.labels)))
    overlap = pool.image_paths & {str(Path(ref).resolve()) for ref in model.index.references}
    if overlap:
        raise ValueError(f"{len(overlap)} test images are also model references")
    return {"perception": FathomNetPerception(model), "image_pool": pool}


def load_fathomnet(manifest_path: str | Path, artifact_dir: str | Path) -> dict:
    """Load the saved DINOv2 model offline. Needs the perception package and PyTorch."""
    from perception import Perception
    from perception.embed import CachedEncoder, DinoV2Encoder

    model = Perception.load(artifact_dir, CachedEncoder(DinoV2Encoder(offline=True)))
    return build_kit(model, manifest_path)
