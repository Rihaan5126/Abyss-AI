"""Planner-facing API: image inputs only, with no simulator labels or world state."""

from dataclasses import asdict, dataclass
import json
import hashlib
import time
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
        return self.predict_with_evidence(image)[0]

    @property
    def artifact_id(self):
        digest = hashlib.sha256(self.index.embeddings.tobytes())
        digest.update(json.dumps([self.encoder.identity, self.index.labels, self.threshold, self.neighbors]).encode())
        return digest.hexdigest()

    def predict_with_evidence(self, image):
        started = time.perf_counter()
        embeddings = self.encoder.encode([image])
        from .novelty import unit_vectors
        distances, indices = self.index._nn.kneighbors(unit_vectors(embeddings), n_neighbors=self.neighbors)
        neighbors, votes = [], {}
        for distance, index in zip(distances[0], indices[0]):
            distance, index = float(np.clip(distance, 0, 2)), int(index)
            label = self.index.labels[index]
            weight = 1 / max(distance, 1e-6)
            votes[label] = votes.get(label, 0.) + weight
            neighbors.append({'reference': self.index.references[index], 'label': label,
                              'distance': distance, 'similarity': 1-distance, 'weight': weight})
        score = neighbors[0]['distance']
        winner = max(votes, key=votes.get)
        unknown = score > self.threshold
        result = PerceptionResult(
            predicted_category=None if unknown else winner,
            similarity_score=1 - score,
            novelty_score=score,
            is_unknown=unknown,
            image_reference=str(image) if isinstance(image, (str, Path)) else None,
            nearest_reference=neighbors[0]['reference'],
        )
        return result, {'artifact_id': self.artifact_id, 'encoder': self.encoder.identity,
                        'neighbors_used': self.neighbors, 'neighbors': neighbors, 'votes': votes,
                        'vote_winner': winner, 'threshold': self.threshold,
                        'result': {k:v for k,v in result.to_dict().items() if k not in ('image_reference','nearest_reference')},
                        'embedding_cached': getattr(self.encoder, 'last_cache_hits', [None])[0],
                        'processing_ms': (time.perf_counter()-started)*1000,
                        'timing_scope': 'Image encoding/cache lookup and reference matching; excludes model loading'}

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
