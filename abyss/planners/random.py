"""Random baseline: a uniformly random feasible waypoint that has not been surveyed."""

from __future__ import annotations

import numpy as np

from ..contract import HOME, Observation, PublicMap, PublicState, Target
from .base import Planner


class RandomPlanner(Planner):
    name = "random"

    def reset(self, public_map: PublicMap, config: dict, seed: int) -> None:
        self._rng = np.random.default_rng(seed)

    def choose_target(
        self, public_state: PublicState, observation_history: tuple[Observation, ...]
    ) -> Target:
        candidates = np.argwhere(public_state.feasible & ~public_state.surveyed)
        if len(candidates) == 0:
            return HOME
        row, col = candidates[self._rng.integers(len(candidates))]
        return int(row), int(col)
