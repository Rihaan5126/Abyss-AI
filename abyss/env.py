"""Simulator: owns hidden ecology, movement, energy and mission completion.

Planners get PublicMap, PublicState and Observation, never this object.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from .config import SimConfig
from .contract import (
    HOME,
    Cell,
    ImagePool,
    MissionStatus,
    Observation,
    Perception,
    PublicMap,
    PublicState,
    StepResult,
    Target,
)
from .robot import RobotState, TravelGraph
from .terrain import FEATURE_NAMES, Terrain, generate_synthetic_terrain, load_gebco_terrain
from .world import STREAM_TERRAIN, HiddenWorld, generate_world, stream


@dataclass(frozen=True)
class _Perceived:
    """What the robot perceives at a cell, plus private records for the evaluator."""

    categories: tuple[str, ...]
    image_refs: tuple[str, ...] = ()
    image_labels: tuple[str | None, ...] = ()
    novelty_scores: tuple[float, ...] = ()
    unknown_flags: tuple[bool, ...] = ()
    records: tuple[dict, ...] = ()


def _read_only_copy(values: np.ndarray) -> np.ndarray:
    copy = np.array(values)
    copy.setflags(write=False)
    return copy


class Environment:
    def __init__(
        self,
        config: SimConfig,
        terrain: Terrain | None = None,
        perception: Perception | None = None,
        image_pool: ImagePool | None = None,
    ) -> None:
        if (config.perception_mode == "real") != (perception is not None and image_pool is not None):
            raise ValueError("perception and image_pool are required for real mode, and only then")
        self.config = config
        self._perception = perception
        self._image_pool = image_pool
        self._fixed_terrain = terrain
        self.seed: int | None = None
        self.public_map: PublicMap | None = None

    def reset(self, seed: int) -> PublicState:
        config = self.config
        self.seed = seed
        terrain = self._fixed_terrain or self._make_terrain(seed)
        self._terrain = terrain
        names = None
        if self._image_pool is not None:
            self._validate_image_pool()
            names = tuple(self._image_pool.categories)
        self._world: HiddenWorld = generate_world(terrain, config, seed, names)
        self._surveys_by_cell: dict[Cell, _Perceived] = {}
        self._unknown_refs: set[str] = set()
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

    def _validate_image_pool(self) -> None:
        pool = self._image_pool
        unknown_withheld = set(pool.withheld) - set(pool.categories)
        if unknown_withheld:
            raise ValueError(f"Withheld categories not in the pool: {sorted(unknown_withheld)}")
        for category in pool.categories:
            refs = pool.images_for(category)
            if not refs:
                raise ValueError(f"No images for category {category!r}")
            for ref in refs:
                # Refs reach the planner, so a name in a path would leak the true label.
                for name in pool.categories:
                    if name.lower() in ref.lower():
                        raise ValueError(f"Image ref {ref!r} reveals category {name!r}")

    def _perceive(self, cell: Cell) -> _Perceived:
        """Run the model on the images at a cell, once per cell.

        Image choice depends only on the world seed, cell and category, so every planner
        and every repeat survey gets the same images and results.
        """
        if cell in self._surveys_by_cell:
            return self._surveys_by_cell[cell]
        records, results = [], []
        for category in self._world.categories_at(cell):
            refs = self._image_pool.images_for(category)
            key = f"{self.seed}|{cell[0]}|{cell[1]}|{category}".encode()
            choice = int.from_bytes(hashlib.sha256(key).digest()[:8], "big") % len(refs)
            ref = refs[choice]
            result = self._perception.predict(self._image_pool.load(ref))
            results.append((ref, result))
            records.append(
                {
                    "image_ref": ref,
                    "true_category": category,
                    "withheld": category in self._image_pool.withheld,
                    "predicted_category": result.predicted_category,
                    "is_unknown": bool(result.is_unknown),
                    "novelty_score": float(result.novelty_score),
                }
            )
        known = (r.predicted_category for _, r in results if not r.is_unknown)
        perceived = _Perceived(
            categories=tuple(dict.fromkeys(c for c in known if c is not None)),
            image_refs=tuple(ref for ref, _ in results),
            image_labels=tuple(r.predicted_category for _, r in results),
            novelty_scores=tuple(float(r.novelty_score) for _, r in results),
            unknown_flags=tuple(bool(r.is_unknown) for _, r in results),
            records=tuple(records),
        )
        self._surveys_by_cell[cell] = perceived
        return perceived

    def _make_terrain(self, seed: int) -> Terrain:
        config = self.config
        if config.terrain_source == "gebco":
            terrain = load_gebco_terrain(config.gebco_path)
            if terrain.depth_m.shape != (config.height, config.width):
                raise ValueError(
                    f"GEBCO crop is {terrain.depth_m.shape}, "
                    f"config expects {(config.height, config.width)}"
                )
            return terrain
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
            unknown_encounters=len(self._unknown_refs),
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
        if self.config.perception_mode == "real":
            perceived = self._perceive(cell)
        else:
            perceived = _Perceived(categories=true_categories)
        new = tuple(c for c in perceived.categories if c not in self._robot.discovered)
        self._robot.discovered.extend(new)
        self._unknown_refs.update(
            ref for ref, unknown in zip(perceived.image_refs, perceived.unknown_flags) if unknown
        )

        observation = Observation(
            step=self._step,
            waypoint=cell,
            feature_names=FEATURE_NAMES,
            features=tuple(float(v) for v in self._terrain.features[cell]),
            categories=perceived.categories,
            energy_cost=survey,
            perception_mode=self.config.perception_mode,
            image_refs=perceived.image_refs,
            novelty_scores=perceived.novelty_scores,
            unknown_flags=perceived.unknown_flags,
            image_labels=perceived.image_labels,
        )
        self._true_observations.append(
            {
                "step": self._step,
                "waypoint": list(cell),
                "categories": list(true_categories),
                "images": list(perceived.records),
            }
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

    def _perception_summary(self) -> dict | None:
        """Scores for images seen this mission, or None under ideal perception."""
        if self._perception is None:
            return None
        images = [image for obs in self._true_observations for image in obs["images"]]
        familiar = [i for i in images if not i["withheld"]]
        withheld = [i for i in images if i["withheld"]]

        def rate(hits: int, total: int) -> float | None:
            return hits / total if total else None

        correct = sum(
            not i["is_unknown"] and i["predicted_category"] == i["true_category"] for i in familiar
        )
        return {
            "model": self._perception.name,
            "images": len(images),
            "familiar_images": len(familiar),
            "familiar_accuracy": rate(correct, len(familiar)),
            "withheld_images": len(withheld),
            "unknown_recall": rate(sum(i["is_unknown"] for i in withheld), len(withheld)),
            "false_novelty_rate": rate(sum(i["is_unknown"] for i in familiar), len(familiar)),
        }

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
            "perception_mode": self.config.perception_mode,
            "withheld_categories": list(self._image_pool.withheld) if self._image_pool else [],
            "perception_summary": self._perception_summary(),
            "true_observations": self._true_observations,
            "true_distinct_categories": found,
            "true_distinct_count": len(found),
            "categories_available_count": int(available.sum()),
            "expected_richness_map": np.round(world.probability.sum(axis=-1), 4).tolist(),
            "encounter_richness_map": world.encounters.sum(axis=-1).tolist(),
        }
