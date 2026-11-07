"""Public terrain: synthetic for now, with GEBCO crops going through terrain_from_depth."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter, uniform_filter

FEATURE_NAMES = ("depth", "slope", "bpi")
BPI_WINDOW = 5
GEBCO_CITATION = (
    "GEBCO Compilation Group (2025) GEBCO 2025 Grid "
    "(doi:10.5285/37c52e96-24ea-67ce-e063-7086abc05f29)"
)


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


def load_gebco_terrain(path: str | Path) -> Terrain:
    """Load a crop written by scripts/fetch_gebco.py. Row 0 is the northern edge."""
    crop = json.loads(Path(path).read_text(encoding="utf-8"))
    return terrain_from_depth(
        -np.array(crop["elevation_m"], dtype=float),
        crop["cell_height_m"],
        "gebco_2025",
        crop["cell_width_m"],
    )


def terrain_from_depth(
    depth_m: np.ndarray, cell_size_m: float, source: str, cell_width_m: float | None = None
) -> Terrain:
    """Derive slope and bathymetric position from a positive-down depth grid.

    ``cell_size_m`` is the north-south spacing. Pass ``cell_width_m`` when east-west
    spacing differs, as it does for latitude-longitude grids away from the equator.
    """
    depth = np.asarray(depth_m, dtype=float)
    elevation = -depth
    d_row, d_col = np.gradient(elevation, cell_size_m, cell_width_m or cell_size_m)
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
