"""Test planners and shared fixtures."""

from __future__ import annotations

import numpy as np

from abyss.config import SCENARIOS
from abyss.contract import HOME
from abyss.planners.base import Planner

ALL_SCENARIOS = SCENARIOS
SEEDS = (0, 1, 2)


class FarthestPlanner(Planner):
    """Stress test: always picks the most expensive feasible target."""

    name = "farthest"

    def reset(self, public_map, config, seed):
        pass

    def choose_target(self, public_state, observation_history):
        if not public_state.feasible.any():
            return HOME
        costs = np.where(public_state.feasible, public_state.travel_cost, -1.0)
        row, col = np.unravel_index(int(np.argmax(costs)), costs.shape)
        return int(row), int(col)


class RepeatPlanner(Planner):
    """Surveys the same waypoint until it can no longer afford to."""

    name = "repeat"

    def __init__(self, cell=(3, 3)):
        self.cell = cell

    def reset(self, public_map, config, seed):
        pass

    def choose_target(self, public_state, observation_history):
        return self.cell if public_state.feasible[self.cell] else HOME


class RoguePlanner(Planner):
    """Ignores the feasibility mask and asks for a fixed target."""

    name = "rogue"

    def __init__(self, target):
        self.target = target

    def reset(self, public_map, config, seed):
        pass

    def choose_target(self, public_state, observation_history):
        return self.target
