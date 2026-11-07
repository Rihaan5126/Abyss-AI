"""Extra synthetic landforms for the replay demo: hills, dips and steep walls.

These are illustrative shapes, not real places, and they are not part of the
6,300-mission benchmark. Each one is fixed by its own seed, which was not chosen by
mission outcome. Relief stays within about 2,100 m, close to the GEBCO crop's, so the
3D view keeps a similar scale.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

from .terrain import Terrain, _standardise, terrain_from_depth

LANDFORM_SEED = 7


def _grid(shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    height, width = shape
    rows, cols = np.mgrid[0:height, 0:width].astype(float)
    return rows / max(height - 1, 1), cols / max(width - 1, 1)


def _texture(rng: np.random.Generator, shape: tuple[int, int], sigma) -> np.ndarray:
    return _standardise(gaussian_filter(rng.normal(size=shape), sigma=sigma, mode="reflect"))


def _bump(y: np.ndarray, x: np.ndarray, cy: float, cx: float, radius: float) -> np.ndarray:
    return np.exp(-(((y - cy) ** 2 + (x - cx) ** 2) / radius**2))


def seamount(shape, rng):
    """A volcanic peak rising from the plain, with a smaller cone and flank ridges."""
    y, x = _grid(shape)
    angle = np.arctan2(y - 0.55, x - 0.6)
    flanks = 1.0 + 0.18 * np.cos(5.0 * angle)
    peak = 1500.0 * _bump(y, x, 0.55, 0.6, 0.24) * flanks
    cone = 600.0 * _bump(y, x, 0.2, 0.25, 0.1)
    plain = 1900.0 + 150.0 * y
    return plain - peak - cone + 45.0 * _texture(rng, shape, 1.2)


def abyssal_hills(shape, rng):
    """Long parallel hills and troughs, the most common landform on the deep seafloor."""
    y, x = _grid(shape)
    stretched = _texture(rng, shape, (0.9, 3.5))
    rolling = _texture(rng, shape, 2.5)
    return 1500.0 + 300.0 * x + 260.0 * stretched + 120.0 * rolling


def trench(shape, rng):
    """A shelf that breaks into a steep wall and a deep, curving trench."""
    y, x = _grid(shape)
    axis = 0.62 + 0.08 * np.sin(2.0 * np.pi * y * 0.8)
    wall = 1.0 / (1.0 + np.exp(-(x - axis + 0.12) / 0.05))
    floor = 1000.0 * np.exp(-(((x - axis) / 0.09) ** 2))
    return 350.0 + 700.0 * wall + floor - 250.0 * np.clip(x - axis, 0.0, None) + 40.0 * _texture(rng, shape, 1.0)


def basin(shape, rng):
    """An enclosed dip ringed by a raised rim, with small mounds on its floor."""
    y, x = _grid(shape)
    distance = np.hypot(y - 0.55, x - 0.55)
    bowl = 1100.0 * np.exp(-((distance / 0.3) ** 2))
    rim = 280.0 * np.exp(-(((distance - 0.42) / 0.07) ** 2))
    mounds = 230.0 * (_bump(y, x, 0.5, 0.45, 0.06) + _bump(y, x, 0.62, 0.66, 0.05))
    return 650.0 + bowl - rim - mounds + 50.0 * _texture(rng, shape, 1.5)


LANDFORMS = {
    "seamount": seamount,
    "abyssal_hills": abyssal_hills,
    "trench": trench,
    "basin": basin,
}


def landform_terrain(name: str, shape: tuple[int, int], cell_size_m: float) -> Terrain:
    """Build one named landform. The source records it as synthetic."""
    if name not in LANDFORMS:
        raise ValueError(f"Unknown landform {name!r}; expected one of {tuple(LANDFORMS)}")
    rng = np.random.default_rng([LANDFORM_SEED, list(LANDFORMS).index(name)])
    depth = np.clip(LANDFORMS[name](shape, rng), 50.0, None)
    return terrain_from_depth(depth, cell_size_m, f"synthetic_{name}")
