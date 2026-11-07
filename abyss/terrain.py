"""Public terrain: synthetic for now, with GEBCO crops going through terrain_from_depth."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter, uniform_filter

FEATURE_NAMES = ("depth", "slope", "bpi")
BPI_WINDOW = 5


def _standardise(values: np.ndarray) -> np.ndarray:
    std = values.std()
    return (values - values.mean()) / std if std > 0 else np.zeros_like(values)


@dataclass(frozen=True, eq=False)
class Terrain:
    depth_m: np.ndarray
    slope_deg: np.ndarray
    bpi_m: np.ndarray
    features: np.ndarray  # (H, W, 3) standardised using terrain values only
    cell_size_m: float
    source: str


def terrain_from_depth(depth_m: np.ndarray, cell_size_m: float, source: str) -> Terrain:
    """Derive slope and bathymetric position from a positive-down depth grid."""
    depth = np.asarray(depth_m, dtype=float)
    elevation = -depth
    d_row, d_col = np.gradient(elevation, cell_size_m)
    slope = np.degrees(np.arctan(np.hypot(d_row, d_col)))
    bpi = elevation - uniform_filter(elevation, size=BPI_WINDOW, mode="nearest")
    features = np.stack([_standardise(depth), _standardise(slope), _standardise(bpi)], axis=-1)
    return Terrain(depth, slope, bpi, features, cell_size_m, source)


def generate_synthetic_terrain(
    shape: tuple[int, int], rng: np.random.Generator, cell_size_m: float
) -> Terrain:
    """Procedural shelf-and-canyon seafloor. Plausible in shape, not a real place."""
    height, width = shape
    rows, cols = np.mgrid[0:height, 0:width].astype(float)

    regional = 600.0 + 1400.0 * cols / max(width - 1, 1)

    broad = _standardise(gaussian_filter(rng.normal(size=shape), sigma=4.0, mode="reflect"))
    ridges = _standardise(gaussian_filter(rng.normal(size=shape), sigma=1.5, mode="reflect"))

    phase = rng.uniform(0.0, 2.0 * np.pi)
    start = rng.uniform(0.3, 0.7) * width
    axis = start + 0.15 * width * np.sin(2.0 * np.pi * rows / height + phase)
    canyon = 900.0 * np.exp(-(((cols - axis) / (0.08 * width)) ** 2))

    depth = regional + 250.0 * broad + 90.0 * ridges + canyon
    return terrain_from_depth(np.clip(depth, 50.0, None), cell_size_m, "synthetic")
