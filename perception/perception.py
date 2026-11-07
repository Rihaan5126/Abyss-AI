"""Planner-facing API: image inputs only, with no simulator labels or world state."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path

import numpy as np
from PIL import Image

from .embed import Encoder
from .novelty import ReferenceIndex


@dataclass(frozen=True)
class PerceptionResult:
    predicted_category: str | None
    similarity_score: float
    novelty_score: float
    is_unknown: bool
    image_reference: str | None
    nearest_reference: str

    def to_dict(self) -> dict:
        return asdict(self)


class Perception:
    def __init__(self, encoder: Encoder, index: ReferenceIndex, threshold: float, neighbors: int = 1):
        if not np.isfinite(threshold) or not 0 <= threshold <= 2:
            raise ValueError("Novelty threshold must be a finite cosine distance in [0, 2]")
        self.encoder, self.index, self.threshold = encoder, index, float(threshold)
        if not isinstance(neighbors, int) or not 1 <= neighbors <= len(index.labels):
            raise ValueError('Invalid reference neighbor count')
        self.neighbors = neighbors

    def predict(self, image: str | Path | Image.Image) -> PerceptionResult:
        embeddings = self.encoder.encode([image])
        scores, indices = self.index.query(embeddings)
        score, index = float(scores[0]), int(indices[0])
        unknown = score > self.threshold
        return PerceptionResult(
            predicted_category=None if unknown else self.index.classify(embeddings, self.neighbors)[0],
            similarity_score=1 - score,
            novelty_score=score,
            is_unknown=unknown,
            image_reference=str(image) if isinstance(image, (str, Path)) else None,
            nearest_reference=self.index.references[index],
        )

    def save(self, directory: str | Path):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "references.npy", self.index.embeddings, allow_pickle=False)
        (directory / "metadata.json").write_text(json.dumps({
            "schema_version": 1 if self.neighbors == 1 else 2, "encoder": self.encoder.identity,
            "threshold": self.threshold, "labels": self.index.labels,
            "references": self.index.references,
            "neighbors": self.neighbors,
        }, indent=2) + "\n")

    @classmethod
    def load(cls, directory: str | Path, encoder: Encoder):
        directory = Path(directory)
        metadata = json.loads((directory / "metadata.json").read_text())
        if metadata["schema_version"] not in (1, 2) or metadata["encoder"] != encoder.identity:
            raise ValueError("Reference index uses a different encoder or schema")
        index = ReferenceIndex(
            np.load(directory / "references.npy", allow_pickle=False),
            metadata["labels"], metadata["references"],
        )
        return cls(encoder, index, metadata["threshold"], metadata.get('neighbors', 1))
