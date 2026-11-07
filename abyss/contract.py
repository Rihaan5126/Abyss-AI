"""Shared integration contract. Tell Rihaan, Cam and Ammar before changing it.

Everything here is safe to hand to a planner. Hidden ecology lives in
``abyss.world.HiddenWorld`` and is only reachable by the simulator and evaluator.
That includes the scenario name and rho: they describe the hidden world, so they
never appear in ``PublicMap`` or ``PublicState``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import numpy as np

SCHEMA_VERSION = "1.0"

#: Target value meaning "travel home and end the mission".
HOME = "HOME"

Cell = tuple[int, int]
Target = Cell | str


class MissionStatus(str, Enum):
    RUNNING = "running"
    COMPLETE = "complete"


@dataclass(frozen=True, eq=False)
class PublicMap:
    """Terrain and vehicle facts known before the mission. Arrays are read-only."""

    shape: tuple[int, int]
    home: Cell
    feature_names: tuple[str, ...]
    features: np.ndarray  # (H, W, F), standardised from terrain alone
    depth_m: np.ndarray  # (H, W)
    slope_deg: np.ndarray  # (H, W)
    bpi_m: np.ndarray  # (H, W), positive on ridges
    cell_size_m: float
    terrain_source: str
    energy_budget: float
    survey_cost: float
    energy_reserve: float
    return_cost: np.ndarray  # (H, W), travel cost from each cell to home


@dataclass(frozen=True, eq=False)
class PublicState:
    """What the robot knows right now. Arrays are read-only copies."""

    step: int
    status: MissionStatus
    position: Cell
    home: Cell
    energy_remaining: float
    energy_used: float
    travel_cost: np.ndarray  # (H, W), cost from the current position to each cell
    feasible: np.ndarray  # (H, W) bool, cells the simulator would accept as targets
    surveyed: np.ndarray  # (H, W) bool
    transited: np.ndarray  # (H, W) bool, passed through or surveyed
    discovered: tuple[str, ...]  # distinct categories as perceived by the robot


@dataclass(frozen=True)
class Observation:
    """Result of one local survey.

    ``categories`` are true labels in ideal perception and model predictions in
    real perception. In real mode the true labels stay in the evaluation record.
    """

    step: int
    waypoint: Cell
    feature_names: tuple[str, ...]
    features: tuple[float, ...]
    categories: tuple[str, ...]
    energy_cost: float
    perception_mode: str = "ideal"
    image_refs: tuple[str, ...] = ()
    novelty_scores: tuple[float, ...] = ()
    unknown_flags: tuple[bool, ...] = ()

    @property
    def richness(self) -> int:
        """Distinct categories in this survey: the habitat model's target."""
        return len(set(self.categories))


@dataclass(frozen=True, eq=False)
class StepResult:
    state: PublicState
    accepted: bool
    target: Target
    reason: str = ""  # why a target was rejected; rejected steps cost no energy
    route: tuple[Cell, ...] = ()
    energy_travel: float = 0.0
    energy_survey: float = 0.0
    observation: Observation | None = None
    new_discoveries: tuple[str, ...] = ()

    @property
    def done(self) -> bool:
        return self.state.status is MissionStatus.COMPLETE


@dataclass(frozen=True)
class PerceptionResult:
    """Output of Ammar's perception module for one image."""

    predicted_category: str | None
    similarity: float
    novelty_score: float
    is_unknown: bool
    image_ref: str


class Perception(Protocol):
    def predict(self, image: object) -> PerceptionResult: ...
