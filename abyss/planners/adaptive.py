"""ABYSS adaptive planner: online Bayesian habitat model plus energy-aware utility.

    U(x) = ( max(0, y_hat(x)) + beta * I(x) + gamma * C(x) ) / ( E_travel(x) + E_survey + eps )

y_hat  Bayesian linear prediction of local observed richness (``Observation.richness``)
I      information gain 0.5 * log(1 + phi^T Sigma phi / noise_var)
C      coverage incentive, min(1, distance to nearest surveyed cell / coverage_radius)

Only cells the simulator marks feasible and that have not been surveyed are scored.
There are no scripted reactions: the route changes only because the posterior changes.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt

from ..contract import HOME, Observation, PublicMap, PublicState, Target
from ..learning.bayesian import BayesianLinearRegression, quadratic_features
from .base import Planner

# Frozen 2026-11-07 after `python -m abyss.evaluation.tune` on development seeds 0-19.
# Across 27 settings the spread in mean distinct categories was within seed noise
# (12.74 here vs 12.80 best), and habitat coverage did not help, so the original
# defaults were kept rather than fitting noise. Do not retune on seeds >= 1000.
DEFAULTS: dict = {
    "beta": 1.0,  # information-gain weight
    "gamma": 0.5,  # coverage weight
    "coverage": "spatial",  # spatial | habitat | both (mean of the two)
    "coverage_radius": 3.0,  # cells, for spatial coverage
    "habitat_radius": 1.0,  # standardised feature units, for habitat coverage
    "noise_var": 1.0,
    "prior_precision": 1.0,
    "bias_prior_precision": 0.1,
    "squared": ("depth", "slope"),
    "learn": True,  # ablation: False freezes the model at its prior
    "eps": 1e-6,
}


class AdaptivePlanner(Planner):
    name = "abyss"
    overrides: dict = {}  # ablation subclasses change defaults here

    def reset(self, public_map: PublicMap, config: dict, seed: int) -> None:
        self.config = {**DEFAULTS, **self.overrides, **(config or {})}
        c = self.config
        self.survey_cost = public_map.survey_cost
        self.features = np.asarray(public_map.features, float)
        self.phi,self.phi_names = quadratic_features(
            public_map.features, public_map.feature_names, tuple(c["squared"])
        )
        dim = self.phi.shape[-1]
        precision = np.full(dim, c["prior_precision"], float)
        precision[0] = c["bias_prior_precision"]
        self.model = BayesianLinearRegression(dim, precision, c["noise_var"])
        self._decision: dict = {}

    # learning -----------------------------------------------------------
    def observe(self, observation: Observation) -> None:
        if self.config["learn"]:
            row, col = observation.waypoint
            self.model.update(self.phi[row, col], float(observation.richness))

    def belief(self) -> tuple[np.ndarray, np.ndarray]:
        """Predicted richness and epistemic standard deviation, both (H, W)."""
        mean, var = self.model.predict(self.phi)
        return mean, np.sqrt(var)

    # planning -----------------------------------------------------------
    def _coverage(self, surveyed: np.ndarray) -> np.ndarray:
        """C(x) in [0, 1]: how unlike anything surveyed so far x is.

        spatial: map distance to the nearest surveyed cell.
        habitat: terrain-feature distance to the nearest surveyed habitat, so the robot
        values habitat types it has rarely sampled even when they are far from home.
        """
        if not surveyed.any():
            return np.ones(surveyed.shape)
        c = self.config
        spatial = np.minimum(1.0, distance_transform_edt(~surveyed) / c["coverage_radius"])
        if c["coverage"] == "spatial":
            return spatial
        sampled = self.features[surveyed]  # (N, F)
        diff = self.features[:, :, None, :] - sampled[None, None, :, :]
        habitat = np.minimum(1.0, np.sqrt((diff**2).sum(-1)).min(-1) / c["habitat_radius"])
        if c["coverage"] == "habitat":
            return habitat
        return 0.5 * (spatial + habitat)

    def utility_terms(self, state: PublicState) -> dict[str, np.ndarray]:
        c = self.config
        mean, var = self.model.predict(self.phi)
        info = 0.5 * np.log1p(var / c["noise_var"])
        coverage = self._coverage(state.surveyed)
        cost = state.travel_cost + self.survey_cost
        value = np.maximum(0.0, mean) + c["beta"] * info + c["gamma"] * coverage
        candidates = state.feasible & ~state.surveyed
        utility = np.where(candidates, value / (cost + c["eps"]), -np.inf)
        return {
            "expected_richness": mean,
            "information_gain": info,
            "coverage": coverage,
            "energy_cost": cost,
            "utility": utility,
            "candidates": candidates,
        }

    def choose_target(
        self, public_state: PublicState, observation_history: tuple[Observation, ...]
    ) -> Target:
        terms = self.utility_terms(public_state)
        if not terms["candidates"].any():
            self._decision = {}
            return HOME
        index = int(np.argmax(terms["utility"]))  # deterministic: first max, row-major
        row, col = np.unravel_index(index, terms["utility"].shape)
        self._decision = {
            key: float(terms[key][row, col])
            for key in ("expected_richness", "information_gain", "coverage", "energy_cost", "utility")
        }
        self._decision["candidates"] = int(terms["candidates"].sum())
        return int(row), int(col)

    def diagnostics(self) -> dict:
        mean, std = self.belief()
        return {
            "predicted_richness": np.round(mean, 3),
            "uncertainty": np.round(std, 3),
            "target_utility": self._decision,
            "model": {
                "observations": self.model.n,
                "weights": dict(zip(self.phi_names, np.round(self.model.mean, 4).tolist())),
            },
        }


class NoLearnPlanner(AdaptivePlanner):
    """Ablation: same utility, but the model never updates from observations."""

    name = "abyss-nolearn"
    overrides = {"learn": False}


class NoInfoPlanner(AdaptivePlanner):
    """Ablation: learns, but ignores the information-gain term."""

    name = "abyss-noinfo"
    overrides = {"beta": 0.0}
