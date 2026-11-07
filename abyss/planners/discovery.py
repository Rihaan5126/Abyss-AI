"""Experimental category-aware exploration, using public observations only.

Rare-category habitat is a discovery *proxy*, not a probability of an unseen
species. No list of undiscovered labels is supplied. Shrunk incidence models can
learn terrain niches, spatial patches, or that neither predicts better than a
constant. Route search executes only its first stop and replans after observing.
"""

from __future__ import annotations

import numpy as np
from scipy.special import softmax

from ..contract import HOME, Observation, PublicMap, PublicState, Target
from ..robot import TravelGraph
from .adaptive import AdaptivePlanner


# Candidate selection is recorded separately in docs/discovery-development.json.
DISCOVERY_DEFAULTS = {
    "rarity_power": 1.0,
    "lookahead": 1,
    "warmup_surveys": 5,
    "habitat_bandwidth": 1.0,
    "spatial_bandwidth": 4.0,
    "prior_strength": 2.0,
    "exploration_weight": 0.5,
    "warmup_weight": 2.0,
    "beam_width": 6,
    "candidate_count": 18,
    "robust_vision": True,
    "learn": True,
}


class DiscoveryPlanner(AdaptivePlanner):
    name = "abyss-discovery"

    def reset(self, public_map: PublicMap, config: dict, seed: int) -> None:
        super().reset(public_map, {**DISCOVERY_DEFAULTS, **(config or {})}, seed)
        c = self.config
        if c["rarity_power"] < 0 or c["lookahead"] not in (1, 2, 3):
            raise ValueError("rarity_power must be nonnegative and lookahead must be 1, 2 or 3")
        for key in ("habitat_bandwidth", "spatial_bandwidth", "prior_strength"):
            if c[key] <= 0:
                raise ValueError(f"{key} must be positive")
        for key in ("warmup_surveys", "exploration_weight", "warmup_weight"):
            if c[key] < 0:
                raise ValueError(f"{key} must be nonnegative")
        for key in ("beam_width", "candidate_count"):
            if not isinstance(c[key], int) or c[key] < 1:
                raise ValueError(f"{key} must be a positive integer")
        self.public_map = public_map
        self._graph = (None if public_map.terrain_cost_factor is None else
                       TravelGraph(public_map.depth_m, public_map.terrain_cost_factor))
        self._cost_cache: dict[tuple[int, int], np.ndarray] = {}
        self._cells: list[tuple[int, int]] = []
        self._labels: list[set[str]] = []
        self._real: list[bool] = []
        self._reliability: list[float] = []
        self._label_refs: dict[str, set[str]] = {}
        self._unknown_refs: set[str] = set()
        self._unknown_targets: list[float] = []
        self._losses = np.zeros(3)  # global, terrain, spatial; prequential Brier loss
        self._surveys_seen = 0
        self._prediction_cache = None
        self._selected_categories: list[dict] = []

    def _kernels(self, cells: np.ndarray) -> np.ndarray:
        """Three (query, training) kernels. All inputs are public terrain/locations."""
        train = np.asarray(self._cells, dtype=int)
        query_features = self.features[cells[:, 0], cells[:, 1]]
        train_features = self.features[train[:, 0], train[:, 1]]
        habitat_d2 = ((query_features[:, None] - train_features[None]) ** 2).sum(-1)
        spatial_d2 = ((cells[:, None] - train[None]) ** 2).sum(-1)
        return np.stack((
            np.ones_like(habitat_d2),
            np.exp(-habitat_d2 / (2 * self.config["habitat_bandwidth"] ** 2)),
            np.exp(-spatial_d2 / (2 * self.config["spatial_bandwidth"] ** 2)),
        ))

    def _training(self):
        names = sorted(set().union(*self._labels)) if self._labels else []
        y = np.array([[name in labels for name in names] for labels in self._labels], float)
        # One opaque image repeated at many cells isn't independent confirmation
        # that its predicted label is right. Two different images merely remove
        # this caution; they are not a calibrated accuracy estimate.
        if self.config["robust_vision"]:
            for k, name in enumerate(names):
                if len(self._label_refs.get(name, ())) < 2:
                    y[np.asarray(self._real, bool), k] *= 0.5
        return names, y

    def _predict(self, cells: np.ndarray):
        names, y = self._training()
        if not self._cells:
            return names, np.empty((3, len(cells), 0)), np.ones(len(cells)), np.zeros(len(cells))
        weights = self._kernels(cells) * np.asarray(self._reliability)[None, None, :]
        effective_n = weights.sum(-1)
        prior = (y.sum(0) + 0.5) / (len(y) + 1.0)
        strength = self.config["prior_strength"]
        rates = (weights @ y + strength * prior) / (effective_n[..., None] + strength)
        # Global estimates should stay constant; don't count the prior twice.
        rates[0] = prior
        mix = self._mixture()
        support = (mix[:, None] * effective_n).sum(0)
        uncertainty = 1 / np.sqrt(1 + support)
        unknown = ((weights @ np.asarray(self._unknown_targets)) /
                   (effective_n + strength))
        return names, rates, uncertainty, mix @ unknown

    def _mixture(self):
        # A small fixed global component prevents a few early successes from
        # eliminating the observation-blind model. Losses use past predictions.
        return 0.85 * softmax(-self._losses) + 0.05

    def observe(self, observation: Observation) -> None:
        self._surveys_seen += 1
        if not self.config["learn"]:
            return
        cell = tuple(observation.waypoint)
        labels = set(observation.categories)
        real = observation.perception_mode != "ideal"
        reliability = 1.0
        if self.config["robust_vision"] and real and any(observation.unknown_flags):
            reliability = 0.5  # uncertain observations give weaker absence evidence
        if self._cells:
            names, rates, _, _ = self._predict(np.array([cell]))
            if names:
                target = np.array([name in labels for name in names], float)
                self._losses += reliability * ((rates[:, 0] - target) ** 2).mean(-1)
        new_unknown = 0
        for ref, label, unknown in zip(observation.image_refs, observation.image_labels,
                                       observation.unknown_flags):
            if unknown:
                if ref not in self._unknown_refs:
                    new_unknown += 1
                    self._unknown_refs.add(ref)
            elif label is not None:
                self._label_refs.setdefault(label, set()).add(ref)
        if self.config["robust_vision"]:
            unknown_target = min(0.25, 0.25 * new_unknown)
        else:
            unknown_target = float(sum(observation.unknown_flags))
        self._cells.append(cell)
        self._labels.append(labels)
        self._real.append(real)
        self._reliability.append(reliability)
        self._unknown_targets.append(unknown_target)
        self._prediction_cache = None

    def _maps(self):
        if self._prediction_cache is None:
            cells = np.indices(self.public_map.shape).reshape(2, -1).T
            names, estimates, uncertainty, unknown = self._predict(cells)
            rates = np.einsum("m,mnk->nk", self._mixture(), estimates)
            _, y = self._training()
            counts = y.sum(0) if len(y) else np.empty(0)
            rarity = (1 + counts) ** -self.config["rarity_power"]
            richness = rates.sum(-1)
            opportunity = rates @ rarity + unknown
            self._prediction_cache = (names, rates, rarity, richness, opportunity, uncertainty)
        return self._prediction_cache

    def belief(self) -> tuple[np.ndarray, np.ndarray]:
        """Expose the learned incidence sum, rather than the unused richness prior."""
        _, _, _, richness, _, uncertainty = self._maps()
        return richness.reshape(self.public_map.shape), uncertainty.reshape(self.public_map.shape)

    def utility_terms(self, state: PublicState) -> dict[str, np.ndarray]:
        _, _, _, richness, opportunity, uncertainty = self._maps()
        shape = self.public_map.shape
        coverage = self._coverage(state.surveyed)
        if state.surveyed.any():
            sampled = self.features[state.surveyed]
            d2 = ((self.features[:, :, None] - sampled[None, None]) ** 2).sum(-1).min(-1)
            habitat = 1 - np.exp(-0.5 * d2 / self.config["habitat_bandwidth"] ** 2)
        else:
            habitat = np.ones(shape)
        warmup = self._surveys_seen < self.config["warmup_surveys"]
        # Exploration is an explicit bonus, never labelled expected new species.
        info = uncertainty.reshape(shape) * (0.5 + 0.5 * habitat)
        exploration = self.config["exploration_weight"] * info + 0.1 * coverage
        if warmup:
            exploration += self.config["warmup_weight"] * habitat
        value = opportunity.reshape(shape) + exploration
        cost = state.travel_cost + self.survey_cost
        candidates = state.feasible & ~state.surveyed
        return {"expected_richness": richness.reshape(shape),
                "discovery_proxy": opportunity.reshape(shape),
                "information_gain": info, "coverage": coverage,
                "habitat_coverage": habitat, "exploration_bonus": exploration,
                "value": value, "energy_cost": cost, "candidates": candidates,
                "utility": np.where(candidates, value / (cost + 1e-6), -np.inf)}

    def _costs_from(self, cell):
        if cell not in self._cost_cache:
            self._cost_cache[cell] = self._graph.costs_from(cell)[0]
        return self._cost_cache[cell]

    def _route_search(self, state, terms):
        """Bounded beam search with exact public costs and a reserve at every leaf."""
        candidates = np.flatnonzero(terms["candidates"])
        n = self.config["candidate_count"]
        # Include efficient, high-value and nearby cells so travel to a productive
        # patch can be amortised across later stops. Stable ordering breaks ties.
        priorities = (terms["utility"], terms["value"], -terms["energy_cost"])
        pool = []
        for priority in priorities:
            order = candidates[np.argsort(-priority.ravel()[candidates], kind="stable")[:n]]
            pool.extend(int(i) for i in order)
        pool = list(dict.fromkeys(pool))
        shape = self.public_map.shape
        coords = [tuple(int(v) for v in np.unravel_index(i, shape)) for i in pool]
        best = (float("-inf"), (), 0.0)
        beam = [((), 0.0, 0.0, np.ones(len(self._maps()[0])))]
        names, rates, rarity, *_ = self._maps()
        horizon = self.config["lookahead"] if self._graph is not None else 1
        for _ in range(horizon):
            expanded = []
            for path, spent, reward, survival in beam:
                travel = state.travel_cost if not path else self._costs_from(coords[path[-1]])
                for j, (index, cell) in enumerate(zip(pool, coords)):
                    if j in path:
                        continue
                    cost = spent + float(travel[cell]) + self.survey_cost
                    if cost + self.public_map.return_cost[cell] + self.public_map.energy_reserve > state.energy_remaining + 1e-9:
                        continue
                    # Repeated predicted labels lose marginal value along a route.
                    category_reward = float((rates[index] * rarity * survival).sum())
                    extra = float(terms["value"].flat[index] - (rates[index] @ rarity))
                    # Near-identical habitats share some exploration value too.
                    if path:
                        d2 = min(float(((self.features[cell] - self.features[coords[p]]) ** 2).sum()) for p in path)
                        extra *= 0.5 + 0.5 * (1 - np.exp(-0.5 * d2))
                    total = reward + category_reward + extra
                    score = total / (cost + 1e-6)
                    route = (*path, j)
                    if score > best[0]:
                        best = (score, route, cost)
                    expanded.append((score, route, cost, total, survival * (1 - rates[index])))
            expanded.sort(key=lambda b: -b[0])
            beam = [(p, c, r, s) for _, p, c, r, s in expanded[:self.config["beam_width"]]]
            if not beam:
                break
        if not best[1]:
            return None
        return coords[best[1][0]], [coords[p] for p in best[1]], best[0], best[2]

    def choose_target(self, public_state: PublicState, observation_history: tuple[Observation, ...]) -> Target:
        terms = self.utility_terms(public_state)
        if not terms["candidates"].any():
            self._decision = {}
            self._selected_categories = []
            return HOME
        route = self._route_search(public_state, terms)
        if route is None:
            self._decision = {}
            self._selected_categories = []
            return HOME
        cell, stops, score, cost = route
        self._decision = {key: float(terms[key][cell]) for key in (
            "expected_richness", "discovery_proxy", "information_gain", "coverage",
            "habitat_coverage", "exploration_bonus", "energy_cost", "utility")}
        self._decision.update(candidates=int(terms["candidates"].sum()), route_score=score,
                              planned_stops=stops, planned_energy=cost,
                              warmup=int(self._surveys_seen < self.config["warmup_surveys"]))
        names, rates, rarity, *_ = self._maps()
        index = np.ravel_multi_index(cell, self.public_map.shape)
        order = np.argsort(-(rates[index] * rarity), kind="stable")[:5]
        self._selected_categories = [{"label": names[k], "occurrence_estimate": float(rates[index, k]),
                                      "rarity_weight": float(rarity[k])} for k in order]
        return cell

    def diagnostics(self) -> dict:
        names, _, _, richness, opportunity, uncertainty = self._maps()
        shape = self.public_map.shape
        return {"predicted_richness": np.round(richness.reshape(shape), 3),
                "discovery_proxy": np.round(opportunity.reshape(shape), 3),
                "uncertainty": np.round(uncertainty.reshape(shape), 3),
                "target_utility": self._decision,
                "model": {"observations": len(self._cells), "categories_modelled": len(names),
                          "kind": "shrunk category incidence; rare-habitat discovery proxy",
                          "mixture": dict(zip(("global", "terrain", "spatial"), self._mixture().tolist())),
                          "target_categories": self._selected_categories,
                          "robust_vision": self.config["robust_vision"]}}


class DiscoveryNoLearnPlanner(DiscoveryPlanner):
    name = "abyss-discovery-nolearn"
    overrides = {"learn": False}

    def reset(self, public_map, config, seed):
        super().reset(public_map, {"learn": False, **(config or {})}, seed)


class DiscoveryNoRarityPlanner(DiscoveryPlanner):
    name = "abyss-discovery-norarity"

    def reset(self, public_map, config, seed):
        super().reset(public_map, {"rarity_power": 0.0, **(config or {})}, seed)


class DiscoveryNoLookaheadPlanner(DiscoveryPlanner):
    name = "abyss-discovery-myopic"

    def reset(self, public_map, config, seed):
        super().reset(public_map, {"lookahead": 1, **(config or {})}, seed)


class DiscoveryNoWarmupPlanner(DiscoveryPlanner):
    name = "abyss-discovery-nowarmup"

    def reset(self, public_map, config, seed):
        super().reset(public_map, {"warmup_surveys": 0, **(config or {})}, seed)


class DiscoveryRoutePlanner(DiscoveryPlanner):
    """Keep the three-stop option available even when development favours one stop."""

    name = "abyss-discovery-route"

    def reset(self, public_map, config, seed):
        super().reset(public_map, {"lookahead": 3, **(config or {})}, seed)


class DiscoveryNoVisionGuardPlanner(DiscoveryPlanner):
    name = "abyss-discovery-unguarded"

    def reset(self, public_map, config, seed):
        super().reset(public_map, {"robust_vision": False, **(config or {})}, seed)
