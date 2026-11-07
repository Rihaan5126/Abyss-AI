"""Experimental: aim for where new categories are still being found, not where life is rich.

The richness planner can keep returning to rich habitat full of organisms it already
knows. A probability for each undiscovered category can't be learned, because those
categories have no observations yet. So this planner learns the discovery rate instead:
the same Bayesian model, trained on how many new categories each survey found, with older
surveys gradually forgotten because the target falls as the inventory grows.

Everything else, including the utility and its energy cost, is inherited unchanged.
This does not replace the frozen ABYSS planner or change its results.
"""

from __future__ import annotations

import numpy as np

from ..contract import Observation, PublicMap
from .adaptive import AdaptivePlanner

# Frozen on development seeds by abyss.evaluation.novelty_experiment tune.
NOVELTY_DEFAULTS: dict = {"forgetting": 0.9}


class NoveltyPlanner(AdaptivePlanner):
    name = "abyss-novelty"

    def reset(self, public_map: PublicMap, config: dict, seed: int) -> None:
        super().reset(public_map, {**NOVELTY_DEFAULTS, **(config or {})}, seed)
        self._known: set[str] = set()
        self._phis: list[np.ndarray] = []
        self._targets: list[float] = []

    def observe(self, observation: Observation) -> None:
        if not self.config["learn"]:
            return
        new = set(observation.categories) - self._known
        self._known |= new
        # Each unfamiliar image counts as novel, because it can't be matched to anything known.
        target = len(new) + sum(observation.unknown_flags)
        row, col = observation.waypoint
        self._phis.append(self.phi[row, col])
        self._targets.append(float(target))

        # Refit with weights, so recent surveys say more about the current discovery rate.
        ages = np.arange(len(self._phis) - 1, -1, -1)
        scale = np.sqrt(self.config["forgetting"] ** ages)
        self.model.reset()
        self.model.update(np.array(self._phis) * scale[:, None], np.array(self._targets) * scale)
