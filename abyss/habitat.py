"""Terrain-based habitat classes, for display in logs and the UI only.

Classes cluster public terrain features, and survey events use only cells the robot has
visited. Planners never receive any of this, so it cannot change a route or a result.

These are not biomes. At this grid scale there is no temperature, oxygen or substrate
data, and the biology they appear beside is simulated.
"""

from __future__ import annotations

import os

# scikit-learn's core-count probe prints a long warning on recent Windows versions.
os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))

import numpy as np  # noqa: E402
from sklearn.cluster import KMeans  # noqa: E402

from .contract import PublicMap  # noqa: E402

N_CLASSES = 5
_CLUSTER_SEED = 0
_cache: dict[bytes, dict] = {}


def _describe(depth: float, slope: float, bpi: float) -> str:
    depth_word = "Shallow" if depth < -0.5 else "Deep" if depth > 0.5 else "Mid-depth"
    slope_word = "gentle" if slope < -0.3 else "steep" if slope > 0.6 else "sloping"
    shape = ", ridge" if bpi > 0.5 else ", trough" if bpi < -0.5 else ""
    return f"{depth_word}, {slope_word}{shape}"


def habitat_classes(public_map: PublicMap) -> dict:
    """Cluster terrain into classes, numbered from shallowest to deepest."""
    key = public_map.features.tobytes()
    if key in _cache:
        return _cache[key]

    features = np.asarray(public_map.features, float)
    flat = features.reshape(-1, features.shape[-1])
    model = KMeans(n_clusters=N_CLASSES, n_init=10, random_state=_CLUSTER_SEED).fit(flat)
    depth_index = public_map.feature_names.index("depth")
    order = np.argsort(model.cluster_centers_[:, depth_index])
    rank = np.empty(N_CLASSES, dtype=int)
    rank[order] = np.arange(N_CLASSES)
    centres = model.cluster_centers_[order]

    named = dict(zip(public_map.feature_names, centres.T))
    names: list[str] = []
    for i in range(N_CLASSES):
        name = _describe(named["depth"][i], named["slope"][i], named["bpi"][i])
        repeats = sum(existing.startswith(name) for existing in names)
        names.append(f"{name} {repeats + 1}" if repeats else name)

    result = {
        "method": "k-means on public depth, slope and bathymetric position",
        "note": "Terrain-based classes for display only. Not biomes, and not used by planners.",
        "names": names,
        "classes": rank[model.labels_].reshape(features.shape[:2]).tolist(),
    }
    _cache[key] = result
    return result


def annotate_surveys(steps: list[dict], habitat: dict, public_map: PublicMap) -> None:
    """Add each survey's class, and whether the robot had sampled that class before."""
    features = np.asarray(public_map.features, float)
    sampled_classes: set[int] = set()
    sampled_features: list[np.ndarray] = []
    for step in steps:
        observation = step["observation"]
        if observation is None:
            continue
        row, col = observation["waypoint"]
        habitat_class = habitat["classes"][row][col]
        here = features[row, col]
        distance = (
            float(min(np.linalg.norm(here - other) for other in sampled_features))
            if sampled_features
            else None
        )
        new_class = habitat_class not in sampled_classes
        sampled_classes.add(habitat_class)
        sampled_features.append(here)
        observation["habitat"] = {
            "class": habitat_class,
            "name": habitat["names"][habitat_class],
            "new_class": new_class,
            "classes_sampled": len(sampled_classes),
            "distance_to_sampled": distance,
        }
