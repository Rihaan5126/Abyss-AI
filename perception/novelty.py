"""Cosine reference distance and validation-only novelty calibration."""

import numpy as np
from sklearn.neighbors import NearestNeighbors


def unit_vectors(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float64)
    if vectors.ndim != 2 or not len(vectors) or not np.isfinite(vectors).all():
        raise ValueError("Embeddings must be a nonempty finite 2D array")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if (norms <= 1e-12).any():
        raise ValueError("Zero embeddings cannot define cosine similarity")
    return vectors / norms


class ReferenceIndex:
    def __init__(self, embeddings: np.ndarray, labels: list[str], references: list[str]):
        self.embeddings = unit_vectors(embeddings)
        if len(labels) != len(self.embeddings) or len(references) != len(labels):
            raise ValueError("One label and image reference are required for every embedding")
        if any(not isinstance(label, str) or not label for label in labels):
            raise ValueError("Reference labels must be nonempty strings")
        self.labels = list(labels)
        self.references = list(references)
        self._nn = NearestNeighbors(n_neighbors=1, metric="cosine", algorithm="brute")
        self._nn.fit(self.embeddings)

    def query(self, embeddings: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        distances, indices = self._nn.kneighbors(unit_vectors(embeddings))
        return np.clip(distances[:, 0], 0, 2), indices[:, 0]

    def classify(self, embeddings, neighbors=1):
        if not isinstance(neighbors, int) or not 1 <= neighbors <= len(self.labels):
            raise ValueError('neighbors must be between 1 and the reference count')
        distances, indices = self._nn.kneighbors(unit_vectors(embeddings), n_neighbors=neighbors)
        predictions = []
        for ds, ids in zip(distances, indices):
            votes = {}
            for distance, index in zip(ds, ids):
                label = self.labels[index]
                votes[label] = votes.get(label, 0.) + 1 / max(float(distance), 1e-6)
            predictions.append(max(votes, key=votes.get))  # ties prefer nearest label
        return predictions


def calibrate_threshold(familiar_scores: np.ndarray, false_alert_rate: float = .05) -> float:
    """Higher scores mean less familiar. Unknown iff score > threshold.

    The empirical upper quantile controls alerts on this validation set only;
    it does not guarantee the same false alert rate on unseen images.
    """
    scores = np.asarray(familiar_scores, dtype=float)
    if scores.ndim != 1 or not len(scores) or not np.isfinite(scores).all():
        raise ValueError("Calibration requires finite familiar validation scores")
    if not 0 <= false_alert_rate < 1:
        raise ValueError("false_alert_rate must be in [0, 1)")
    if ((scores < 0) | (scores > 2)).any():
        raise ValueError("Cosine distances must lie in [0, 2]")
    return float(np.quantile(scores, 1 - false_alert_rate, method="higher"))
