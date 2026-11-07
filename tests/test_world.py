"""Each scenario must contain the ecological signal it claims to, and no other."""

from dataclasses import replace

import numpy as np
import pytest
from helpers import ALL_SCENARIOS

from abyss.config import SimConfig
from abyss.env import Environment
from abyss.terrain import generate_synthetic_terrain
from abyss.world import STREAM_TERRAIN, generate_world, stream

SEEDS = range(8)


def _world(scenario, seed, rho=1.0):
    config = SimConfig(scenario=scenario, rho=rho)
    terrain = generate_synthetic_terrain(
        (config.height, config.width), stream(seed, STREAM_TERRAIN), config.cell_size_m
    )
    return terrain, generate_world(terrain, config, seed)


def _morans_i(grid):
    z = grid - grid.mean()
    pairs = (z[:-1, :] * z[1:, :]).sum() + (z[:, :-1] * z[:, 1:]).sum()
    weights = z[:-1, :].size + z[:, :-1].size
    return (grid.size / weights) * pairs / (z**2).sum()


def _slope_correlation(scenario, seed):
    terrain, world = _world(scenario, seed)
    richness = world.probability.sum(axis=-1)
    return np.corrcoef(richness.ravel(), terrain.features[..., 1].ravel())[0, 1]


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_rho_zero_removes_all_signal(scenario):
    _, world = _world(scenario, 0, rho=0.0)
    for k, prevalence in enumerate(world.prevalence):
        assert np.allclose(world.probability[..., k], prevalence)


def test_random_world_has_no_signal_at_any_rho():
    _, world = _world("random", 0, rho=1.0)
    assert np.ptp(world.probability.sum(axis=-1)) < 1e-9
    moran = np.mean([_morans_i(_world("random", s)[1].encounters.sum(-1).astype(float)) for s in SEEDS])
    assert abs(moran) < 0.03


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_prevalence_is_the_same_in_every_scenario(scenario):
    _, world = _world(scenario, 2)
    assert np.allclose(world.probability.mean(axis=(0, 1)), world.prevalence, atol=1e-8)


def test_ridge_favours_steep_terrain_and_reversed_avoids_it():
    assert np.mean([_slope_correlation("ridge", s) for s in SEEDS]) > 0.5
    assert np.mean([_slope_correlation("reversed", s) for s in SEEDS]) < -0.5


def test_clusters_are_spatial_but_not_terrain_driven():
    morans, terrain_corrs = [], []
    for seed in SEEDS:
        terrain, world = _world("clustered", seed)
        richness = world.probability.sum(axis=-1)
        morans.append(_morans_i(richness))
        for i in range(terrain.features.shape[-1]):
            terrain_corrs.append(abs(np.corrcoef(richness.ravel(), terrain.features[..., i].ravel())[0, 1]))
    assert np.mean(morans) > 0.5
    assert np.mean(terrain_corrs) < 0.1


def test_nonlinear_world_is_misspecified_for_the_quadratic_model():
    linear_r2, full_r2 = [], []
    for seed in SEEDS:
        terrain, world = _world("nonlinear", seed)
        target = world.probability.sum(axis=-1).ravel()
        depth, slope, bpi = (terrain.features[..., i].ravel() for i in range(3))
        base = np.column_stack([np.ones_like(depth), depth, slope, bpi, depth**2, slope**2])
        extended = np.column_stack([base, np.tanh(2 * depth) * np.tanh(2 * slope)])
        for design, scores in ((base, linear_r2), (extended, full_r2)):
            coef, *_ = np.linalg.lstsq(design, target, rcond=None)
            scores.append(1 - ((target - design @ coef) ** 2).sum() / ((target - target.mean()) ** 2).sum())
    assert np.mean(linear_r2) < 0.5  # the planned quadratic features miss most of the signal
    assert np.mean(full_r2) > np.mean(linear_r2) + 0.1  # the interaction carries real signal


def test_rho_scales_terrain_signal():
    strengths = []
    for rho in (0.25, 1.0):
        values = []
        for seed in SEEDS:
            terrain, world = _world("ridge", seed, rho=rho)
            values.append(np.ptp(world.probability.sum(axis=-1)))
        strengths.append(np.mean(values))
    assert strengths[1] > strengths[0]


def test_shared_uniforms_keep_rho_zero_worlds_identical_across_scenarios():
    worlds = [_world(s, 3, rho=0.0)[1].encounters for s in ALL_SCENARIOS]
    assert all(np.array_equal(world, worlds[0]) for world in worlds)


def test_fixed_terrain_seed_keeps_terrain_across_world_seeds():
    config = replace(SimConfig(), terrain_seed=11)
    first, second = Environment(config), Environment(config)
    first.reset(1)
    second.reset(2)
    assert np.array_equal(first.public_map.depth_m, second.public_map.depth_m)
    assert not np.array_equal(first._world.encounters, second._world.encounters)
