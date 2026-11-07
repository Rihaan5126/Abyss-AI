"""Category modelling, independent vision evidence, route safety and fair evaluation."""

from dataclasses import replace
import json
from pathlib import Path
import numpy as np
import pytest

from abyss.config import SimConfig
from abyss.contract import HOME, Observation
from abyss.env import Environment
from abyss.evaluation.benchmark import DEFAULT_PLANNERS
from abyss.evaluation.discovery_experiment import (
    CANDIDATES, DEVELOPMENT_SEEDS, EVALUATION_SEEDS, summarise, render,
)
from abyss.planners import PLANNERS
from abyss.planners.discovery import DiscoveryPlanner, DISCOVERY_DEFAULTS
from abyss.run_mission import run_mission, validate_mission_log


def setup(**overrides):
    env = Environment(SimConfig(height=8, width=8, energy_budget=60, terrain_cost_factor=1.7))
    state = env.reset(1)
    planner = DiscoveryPlanner()
    planner.reset(env.public_map, overrides, 0)
    return planner, env, state


def obs(env, cell=(2, 2), labels=("a",), refs=(), flags=(), image_labels=(), mode="ideal", scores=()):
    return Observation(1, cell, env.public_map.feature_names,
                       tuple(env.public_map.features[cell]), labels, 2.0,
                       perception_mode=mode, image_refs=refs, unknown_flags=flags,
                       image_labels=image_labels, novelty_scores=scores)


@pytest.mark.parametrize("name", [n for n in PLANNERS if n.startswith("abyss-discovery")])
def test_all_variants_are_safe_deterministic_and_do_not_repeat(name):
    config = SimConfig(height=8, width=8, energy_budget=50, terrain_cost_factor=2.3)
    log, _ = run_mission(config, PLANNERS[name](), 4)
    validate_mission_log(log)
    assert not log["outcome"]["forced_return"]
    cells = [s["observation"]["waypoint"] for s in log["steps"] if s["observation"]]
    assert len(cells) == len(set(map(tuple, cells))) > 0
    assert log == run_mission(config, PLANNERS[name](), 4)[0]


def test_category_models_learn_presence_absence_and_rarity_from_surveys_only():
    planner, env, _ = setup()
    for cell in ((1, 1), (1, 2), (1, 3), (2, 1)):
        planner.observe(obs(env, cell, ("common",)))
    planner.observe(obs(env, (6, 6), ("rare",)))
    names, rates, rarity, *_ = planner._maps()
    assert set(names) == {"common", "rare"}  # no secret 16-category inventory
    assert rarity[names.index("rare")] > rarity[names.index("common")]
    _, estimates, _, _ = planner._predict(np.array([[1, 1], [6, 6]]))
    assert estimates[2, 0, names.index("common")] > estimates[2, 1, names.index("common")]
    assert np.all((rates >= 0) & (rates <= 1))


def test_repeating_a_category_reduces_its_inventory_weight():
    planner, env, _ = setup()
    planner.observe(obs(env))
    first = planner._maps()[2][0]
    for _ in range(4):
        planner.observe(obs(env))
    assert planner._maps()[2][0] < first


def test_same_image_is_not_independent_label_confirmation():
    planner, env, _ = setup()
    for _ in range(3):
        planner.observe(obs(env, refs=("opaque-1",), flags=(False,), image_labels=("a",), mode="real"))
    assert np.all(planner._training()[1] == 0.5)
    planner.observe(obs(env, refs=("opaque-2",), flags=(False,), image_labels=("a",), mode="real"))
    assert np.all(planner._training()[1] == 1)


def test_unfamiliarity_is_capped_deduplicated_and_not_a_species_or_probability():
    first, env, _ = setup()
    second, _, _ = setup()
    for planner, score in ((first, 0.01), (second, 900.0)):
        observation = obs(env, labels=(), refs=("x", "y", "z"), flags=(True,)*3,
                          image_labels=(None,)*3, mode="real", scores=(score,)*3)
        planner.observe(observation)
        planner.observe(observation)
        assert planner._unknown_targets == [0.25, 0.0]
        assert planner._maps()[0] == []
    np.testing.assert_array_equal(first._maps()[4], second._maps()[4])


def test_lookahead_finds_a_patch_that_a_single_stop_cannot_justify():
    planner, env, state = setup(warmup_surveys=0, exploration_weight=0)
    # A nearby detour pays 2; a distant pair pays 3 + 3. Disjoint predicted
    # categories avoid repeated-label reward. Flattened public navigation costs
    # are used; no encounters or evaluator data construct the decision.
    flat = replace(env.public_map, depth_m=np.zeros((8, 8)), terrain_cost_factor=0.0,
                   return_cost=np.indices((8, 8)).sum(0).astype(float))
    planner.reset(flat, {"lookahead": 3}, 0)
    current_costs = planner._graph.costs_from((0, 0))[0]
    state = replace(state, travel_cost=current_costs, energy_remaining=60)
    cells = ((0, 1), (3, 0), (4, 0))
    rates = np.zeros((64, 8))
    for cell, labels in zip(cells, (slice(0, 2), slice(2, 5), slice(5, 8))):
        rates[np.ravel_multi_index(cell, (8, 8)), labels] = 1
    planner._prediction_cache = (list("abcdefgh"), rates, np.ones(8), rates.sum(1), rates.sum(1), np.zeros(64))
    value = rates.sum(1).reshape(8, 8)
    feasible = np.zeros((8, 8), bool)
    for cell in cells:
        feasible[cell] = True
    terms = {"candidates": feasible, "utility": np.where(feasible, value/(current_costs+2), -np.inf),
             "value": value, "energy_cost": current_costs+2}
    planner.config["lookahead"] = 1
    assert planner._route_search(state, terms)[0] == (0, 1)
    planner.config["lookahead"] = 3
    assert planner._route_search(state, terms)[0] == (3, 0)
    # The productive patch becomes unaffordable once home and reserve are counted.
    assert planner._route_search(replace(state, energy_remaining=10), terms)[0] == (0, 1)


def test_proposed_route_fits_exact_navigation_costs_and_return_reserve():
    planner, env, state = setup(lookahead=3)
    for _ in range(5):
        target = planner.choose_target(state, ())
        if target == HOME:
            break
        stops = planner._decision["planned_stops"]
        spent, previous = 0.0, state.position
        for cell in stops:
            spent += env._graph.costs_from(previous)[0][cell] + env.config.survey_cost
            assert spent + env.public_map.return_cost[cell] + env.config.energy_reserve <= state.energy_remaining + 1e-8
            previous = cell
        assert state.feasible[target]
        result = env.step(target)
        planner.observe(result.observation)
        state = result.state


def test_old_public_maps_fall_back_to_one_step_and_empty_budget_returns_home():
    planner, env, state = setup()
    planner.reset(replace(env.public_map, terrain_cost_factor=None), {}, 0)
    planner.choose_target(state, ())
    assert len(planner._decision["planned_stops"]) == 1
    assert planner.choose_target(replace(state, feasible=np.zeros((8, 8), bool)), ()) == HOME


def test_no_learning_ablation_keeps_category_models_empty_but_finishes_warmup():
    planner, env, state = setup(learn=False, warmup_surveys=1)
    planner.observe(obs(env))
    assert planner._maps()[0] == []
    planner.choose_target(state, ())
    assert not planner._decision["warmup"]


def test_initial_decision_does_not_depend_on_hidden_ecology():
    decisions = []
    for ecology in ("ridge", "random", "reversed"):
        env = Environment(SimConfig(scenario=ecology, height=8, width=8))
        state = env.reset(11)
        planner = DiscoveryPlanner()
        planner.reset(env.public_map, {}, 0)
        decisions.append(planner.choose_target(state, ()))
    assert len(set(decisions)) == 1


def test_official_benchmark_and_experiment_splits_are_unchanged():
    assert not any(p.startswith("abyss-discovery") for p in DEFAULT_PLANNERS)
    assert max(DEVELOPMENT_SEEDS) < min(EVALUATION_SEEDS)
    assert min(EVALUATION_SEEDS) >= 3000
    assert len(CANDIDATES) == 6


def test_experiment_rejects_unpaired_scores_and_bootstraps_complete_seeds():
    rows = []
    for terrain in ("a", "b"):
        for seed in (3000, 3001):
            for planner, value in (("abyss-discovery", 4), ("frontier", 3), ("abyss", 4)):
                rows.append(dict(terrain=terrain, scenario="random", rho=0, seed=seed,
                                 planner=planner, distinct=value, surveys=3, safe=True, forced=False))
    summary = summarise(rows)
    assert summary["aggregate"]["discovery_vs"]["frontier"]["mean_difference"] == 1
    assert summary["safety"]["missions"] == 12
    with pytest.raises(ValueError, match="Unpaired"):
        summarise(rows[:-1])
    with pytest.raises(ValueError, match="Unpaired"):
        summarise([r for r in rows if not (r['terrain'] == 'b' and r['planner'] == 'frontier')])
    with pytest.raises(ValueError, match="duplicate"):
        summarise(rows + [rows[0]])


@pytest.mark.parametrize('stem', ['evaluation', 'landforms', 'vision'])
def test_recorded_reports_match_their_paired_scores_and_frozen_settings(stem):
    path = Path(f'docs/discovery-{stem}.json')
    data = json.loads(path.read_text())
    regenerated = summarise(data['rows'], perception=data['provenance']['perception'],
                            artifact=data['provenance']['artifact'])
    assert regenerated['aggregate'] == data['aggregate']
    assert regenerated['worlds'] == data['worlds']
    assert data['frozen_config'] == DISCOVERY_DEFAULTS
    assert data['safety']['safe_returns'] == data['safety']['missions']
    assert data['safety']['forced_returns'] == 0
    assert path.with_suffix('.md').read_text() == render(data)
    development = json.loads(Path('docs/discovery-development.json').read_text())
    assert development['selected'] == {k: DISCOVERY_DEFAULTS[k] for k in development['selected']}
