"""Simulator: owns hidden ecology, movement, energy and mission completion.

Planners get PublicMap, PublicState and Observation, never this object.
"""

from __future__ import annotations

import numpy as np

from .config import SimConfig
from .contract import (
    HOME,
    Cell,
    MissionStatus,
    Observation,
    PublicMap,
    PublicState,
    StepResult,
    Target,
)
from .robot import RobotState, TravelGraph
from .terrain import FEATURE_NAMES, Terrain, generate_synthetic_terrain
from .world import STREAM_TERRAIN, HiddenWorld, generate_world, stream


def _read_only_copy(values: np.ndarray) -> np.ndarray:
    copy = np.array(values)
    copy.setflags(write=False)
    return copy


class Environment:
    def __init__(self, config: SimConfig, terrain: Terrain | None = None) -> None:
        if config.perception_mode != "ideal":
            raise NotImplementedError("Real perception is not integrated yet")
        self.config = config
        self._fixed_terrain = terrain
        self.seed: int | None = None
        self.public_map: PublicMap | None = None

    def reset(self, seed: int) -> PublicState:
        config = self.config
        self.seed = seed
        terrain = self._fixed_terrain or self._make_terrain(seed)
        self._terrain = terrain
        self._world: HiddenWorld = generate_world(terrain, config, seed)
        self._graph = TravelGraph(terrain.depth_m, config.terrain_cost_factor)
        self._return_cost, self._return_pred = self._graph.costs_from(config.home)
        self.public_map = PublicMap(
            shape=terrain.depth_m.shape,
            home=config.home,
            feature_names=FEATURE_NAMES,
            features=_read_only_copy(terrain.features),
            depth_m=_read_only_copy(terrain.depth_m),
            slope_deg=_read_only_copy(terrain.slope_deg),
            bpi_m=_read_only_copy(terrain.bpi_m),
            cell_size_m=terrain.cell_size_m,
            terrain_source=terrain.source,
            energy_budget=config.energy_budget,
            survey_cost=config.survey_cost,
            energy_reserve=config.energy_reserve,
            return_cost=_read_only_copy(self._return_cost),
        )
        self._robot = RobotState(config.home, config.energy_budget)
        self._status = MissionStatus.RUNNING
        self._step = 0
        self._surveyed = np.zeros(terrain.depth_m.shape, dtype=bool)
        self._transited = np.zeros(terrain.depth_m.shape, dtype=bool)
        self._transited[config.home] = True
        self._true_observations: list[dict] = []
        self._refresh_costs()
        return self._public_state()

    def _make_terrain(self, seed: int) -> Terrain:
        config = self.config
        terrain_seed = seed if config.terrain_seed is None else config.terrain_seed
        return generate_synthetic_terrain(
            (config.height, config.width), stream(terrain_seed, STREAM_TERRAIN), config.cell_size_m
        )

    def _refresh_costs(self) -> None:
        self._travel_cost, self._predecessors = self._graph.costs_from(self._robot.position)
        config = self.config
        # E_remaining >= E_travel + E_survey + E_return + E_reserve
        required = (
            self._travel_cost + config.survey_cost + self._return_cost + config.energy_reserve
        )
        self._feasible = self._robot.energy_remaining >= required

    def _public_state(self) -> PublicState:
        return PublicState(
            step=self._step,
            status=self._status,
            position=self._robot.position,
            home=self.config.home,
            energy_remaining=self._robot.energy_remaining,
            energy_used=self._robot.energy_used,
            travel_cost=_read_only_copy(self._travel_cost),
            feasible=_read_only_copy(self._feasible),
            surveyed=_read_only_copy(self._surveyed),
            transited=_read_only_copy(self._transited),
            discovered=tuple(self._robot.discovered),
        )

    def _reject(self, target: Target, reason: str) -> StepResult:
        return StepResult(self._public_state(), False, target, reason)

    def step(self, target: Target) -> StepResult:
        """Validate a target, then travel and survey it, or travel HOME and finish.

        A rejected target changes nothing and costs nothing.
        """
        if self.public_map is None:
            raise RuntimeError("Call reset() before step()")
        if self._status is not MissionStatus.RUNNING:
            raise RuntimeError("Mission is already complete")
        if isinstance(target, str) and target == HOME:
            return self._return_home()

        try:
            row, col = target
            cell: Cell = (int(row), int(col))
        except (TypeError, ValueError):
            return self._reject(target, "malformed target")
        height, width = self.public_map.shape
        if not (0 <= cell[0] < height and 0 <= cell[1] < width):
            return self._reject(cell, "target outside the grid")
        if not self._feasible[cell]:
            return self._reject(cell, "target violates the energy constraint")
        return self._travel_and_survey(cell)

    def _move(self, route: tuple[Cell, ...], cost: float) -> None:
        self._robot.spend(cost)
        self._robot.position = route[-1]
        for cell in route:
            self._transited[cell] = True

    def _travel_and_survey(self, cell: Cell) -> StepResult:
        travel = float(self._travel_cost[cell])
        route = self._graph.route(self._predecessors, self._robot.position, cell)
        self._move(route, travel)

        survey = self.config.survey_cost
        self._robot.spend(survey)
        self._surveyed[cell] = True
        self._step += 1

        # Encounters are fixed per world, so repeat surveys return the same categories
        # and cannot inflate the distinct-discovery count.
        true_categories = self._world.categories_at(cell)
        new = tuple(c for c in true_categories if c not in self._robot.discovered)
        self._robot.discovered.extend(new)

        observation = Observation(
            step=self._step,
            waypoint=cell,
            feature_names=FEATURE_NAMES,
            features=tuple(float(v) for v in self._terrain.features[cell]),
            categories=true_categories,
            energy_cost=survey,
            perception_mode=self.config.perception_mode,
        )
        self._true_observations.append(
            {"step": self._step, "waypoint": list(cell), "categories": list(true_categories)}
        )
        self._refresh_costs()
        return StepResult(
            self._public_state(), True, cell, "", route, travel, survey, observation, new
        )

    def _return_home(self) -> StepResult:
        position = self._robot.position
        travel = float(self._return_cost[position])
        route = tuple(reversed(self._graph.route(self._return_pred, self.config.home, position)))
        self._move(route, travel)
        self._step += 1
        self._status = MissionStatus.COMPLETE
        self._refresh_costs()
        self._feasible = np.zeros_like(self._feasible)
        return StepResult(self._public_state(), True, HOME, "", route, travel)

    def evaluation_record(self) -> dict:
        """Hidden truth for the trusted evaluator and UI reveal. Never pass to a planner."""
        world = self._world
        found = sorted({c for obs in self._true_observations for c in obs["categories"]})
        available = world.encounters.any(axis=(0, 1))
        return {
            "biology_provenance": "simulated",
            "scenario": world.scenario,
            "rho": world.rho,
            "category_names": list(world.category_names),
            "prevalence": world.prevalence.tolist(),
            "true_observations": self._true_observations,
            "true_distinct_categories": found,
            "true_distinct_count": len(found),
            "categories_available_count": int(available.sum()),
            "expected_richness_map": np.round(world.probability.sum(axis=-1), 4).tolist(),
            "encounter_richness_map": world.encounters.sum(axis=-1).tolist(),
        }
