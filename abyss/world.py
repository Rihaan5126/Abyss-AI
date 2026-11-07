"""Hidden simulated ecology. Only the simulator and evaluator may touch this module.

All biology here is simulated, never observed ground truth.

Each category k at cell x occurs with probability
    p_k(x) = expit(a_k + rho * signal_strength * suitability_k(x))
where a_k is calibrated so the category's mean prevalence is the same in every
scenario and at every rho. Scenarios therefore differ in where organisms are, not
in how many there are. At rho = 0 every p_k is constant, so the world has no
terrain or spatial signal.

Encounters are drawn once per world from uniforms shared across scenarios, so all
planners see identical encounters and repeat surveys return the same result.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.optimize import brentq
from scipy.special import expit

from .config import SimConfig
from .terrain import Terrain

# Independent RNG streams. Sharing one would let a planner's random draws correlate
# with hidden encounters, which is a subtle leak.
STREAM_TERRAIN = 1
STREAM_WORLD = 2
STREAM_PLANNER = 3


def stream(seed: int, stream_id: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence(entropy=seed, spawn_key=(stream_id,)))


@dataclass(frozen=True, eq=False)
class HiddenWorld:
    scenario: str
    rho: float
    category_names: tuple[str, ...]
    prevalence: np.ndarray  # (K,)
    probability: np.ndarray  # (H, W, K)
    encounters: np.ndarray  # (H, W, K) bool

    def categories_at(self, cell: tuple[int, int]) -> tuple[str, ...]:
        present = np.flatnonzero(self.encounters[cell])
        return tuple(self.category_names[i] for i in present)


def _zscore(values: np.ndarray) -> np.ndarray:
    std = values.std()
    return (values - values.mean()) / std if std > 0 else np.zeros_like(values)


def _remove_terrain_signal(field: np.ndarray, features: np.ndarray) -> np.ndarray:
    """Make a spatial field linearly uncorrelated with terrain and its squares."""
    flat = features.reshape(-1, features.shape[-1])
    design = np.column_stack([np.ones(len(flat)), flat, flat**2])
    coef, *_ = np.linalg.lstsq(design, field.ravel(), rcond=None)
    return (field.ravel() - design @ coef).reshape(field.shape)


def _suitability(
    scenario: str,
    terrain: Terrain,
    shared_field: np.ndarray,
    own_field: np.ndarray,
    weight: float,
    depth_niche: float,
) -> np.ndarray:
    depth, slope, bpi = np.moveaxis(terrain.features, -1, 0)
    ridge = weight * (0.8 * slope + 0.2 * bpi)
    niche = -0.5 * (depth - depth_niche) ** 2

    if scenario == "random":
        return np.zeros(depth.shape)
    if scenario == "clustered":
        field = np.sqrt(0.6) * shared_field + np.sqrt(0.4) * own_field
        return _remove_terrain_signal(field, terrain.features)
    if scenario == "ridge":
        return ridge + 0.5 * niche
    if scenario == "reversed":
        return -ridge + 0.5 * niche
    if scenario == "nonlinear":
        # The depth-slope interaction is outside the quadratic feature set on purpose.
        interaction = np.tanh(2.0 * depth) * np.tanh(2.0 * slope)
        return weight * interaction + 0.5 * shared_field
    raise ValueError(f"Unknown scenario {scenario!r}")


def _calibrate_intercept(signal: np.ndarray, prevalence: float) -> float:
    return brentq(lambda a: expit(a + signal).mean() - prevalence, -40.0, 40.0)


def generate_world(
    terrain: Terrain,
    config: SimConfig,
    seed: int,
    category_names: tuple[str, ...] | None = None,
) -> HiddenWorld:
    rng = stream(seed, STREAM_WORLD)
    shape = terrain.depth_m.shape
    n = config.n_categories
    names = category_names or tuple(f"category_{k:02d}" for k in range(n))
    if len(names) != n:
        raise ValueError(f"Got {len(names)} category names, config expects {n}")

    # Draw everything up front so all scenarios share the same random numbers.
    weights = rng.uniform(0.6, 1.0, size=n)
    depth_niches = rng.uniform(-1.5, 1.5, size=n)
    uniforms = rng.random(size=(*shape, n))

    def smooth_field() -> np.ndarray:
        noise = rng.normal(size=shape)
        return _zscore(gaussian_filter(noise, sigma=config.cluster_sigma, mode="reflect"))

    shared_field = smooth_field()
    own_fields = [smooth_field() for _ in range(n)]

    prevalence = np.geomspace(config.prevalence_max, config.prevalence_min, n)
    probability = np.empty((*shape, n))
    for k in range(n):
        suitability = _suitability(
            config.scenario, terrain, shared_field, own_fields[k], weights[k], depth_niches[k]
        )
        signal = config.rho * config.signal_strength * _zscore(suitability)
        intercept = _calibrate_intercept(signal, prevalence[k])
        probability[..., k] = expit(intercept + signal)

    probability.setflags(write=False)
    encounters = uniforms < probability
    encounters.setflags(write=False)
    prevalence.setflags(write=False)

    return HiddenWorld(config.scenario, config.rho, names, prevalence, probability, encounters)
