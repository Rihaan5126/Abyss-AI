"""Safe return is an invariant, whatever the planner does."""

from dataclasses import replace

import numpy as np
import pytest
from helpers import ALL_SCENARIOS, SEEDS, FarthestPlanner, RepeatPlanner, RoguePlanner

from abyss.config import SimConfig
from abyss.contract import HOME
from abyss.env import Environment
from abyss.planners import RandomPlanner
from abyss.run_mission import run_mission, validate_mission_log


@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("planner_type", [RandomPlanner, FarthestPlanner, RepeatPlanner])
def test_missions_return_home_within_budget(scenario, seed, planner_type):
    log, _ = run_mission(SimConfig(scenario=scenario), planner_type(), seed)
    validate_mission_log(log)
    outcome = log["outcome"]
    assert outcome["safe_return"]
    assert outcome["energy_used"] <= log["energy"]["budget"]
    assert not outcome["forced_return"]


def test_return_home_stays_affordable_after_every_step():
    config = SimConfig()
    env = Environment(config)
    state = env.reset(0)
    while state.feasible.any():
        costs = state.feasible * state.travel_cost
        row, col = np.unravel_index(int(costs.argmax()), costs.shape)
        state = env.step((row, col)).state
        needed = env.public_map.return_cost[state.position] + config.energy_reserve
        assert state.energy_remaining >= needed - 1e-9
    assert env.step(HOME).state.energy_remaining >= config.energy_reserve - 1e-9


@pytest.mark.parametrize(
    "target, reason",
    [((99, 99), "outside"), ((-1, 0), "outside"), ("nonsense", "malformed"), (None, "malformed")],
)
def test_invalid_targets_are_rejected_for_free(target, reason):
    env = Environment(SimConfig())
    before = env.reset(0)
    result = env.step(target)
    assert not result.accepted and reason in result.reason
    assert result.state.energy_remaining == before.energy_remaining
    assert result.state.position == before.position


def test_infeasible_target_is_rejected_for_free():
    config = replace(SimConfig(), energy_budget=20.0)
    env = Environment(config)
    before = env.reset(0)
    result = env.step((29, 29))
    assert not result.accepted and "energy" in result.reason
    assert result.state.energy_remaining == before.energy_remaining


def test_rogue_planner_is_sent_home_and_recorded():
    log, _ = run_mission(replace(SimConfig(), energy_budget=20.0), RoguePlanner((29, 29)), 0)
    validate_mission_log(log)
    assert log["outcome"]["forced_return"]
    assert log["outcome"]["rejected_targets"][0]["target"] == [29, 29]


def test_step_after_completion_raises():
    env = Environment(SimConfig())
    env.reset(0)
    env.step(HOME)
    with pytest.raises(RuntimeError):
        env.step(HOME)
