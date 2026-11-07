"""Simulation configuration. Energy values are abstract units, not measured AUV data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

SCENARIOS = ("random", "clustered", "ridge", "reversed", "nonlinear")


@dataclass(frozen=True)
class SimConfig:
    # Grid and terrain
    height: int = 30
    width: int = 30
    cell_size_m: float = 463.0  # about one GEBCO 15-arc-second cell
    terrain_seed: int | None = None  # None: each world seed gets its own terrain
    home: tuple[int, int] = (0, 0)

    # Hidden ecology
    scenario: str = "ridge"
    rho: float = 1.0  # 0 removes all signal, 1 is full strength
    n_categories: int = 16
    prevalence_max: float = 0.25
    prevalence_min: float = 0.01
    signal_strength: float = 2.0
    cluster_sigma: float = 2.5

    # Energy (abstract units)
    energy_budget: float = 150.0
    survey_cost: float = 2.0
    energy_reserve: float = 5.0
    terrain_cost_factor: float = 0.5

    # Perception
    perception_mode: str = "ideal"

    def __post_init__(self) -> None:
        if self.scenario not in SCENARIOS:
            raise ValueError(f"Unknown scenario {self.scenario!r}; expected one of {SCENARIOS}")
        if not 0.0 <= self.rho <= 1.0:
            raise ValueError("rho must be in [0, 1]")
        if self.survey_cost <= 0:
            raise ValueError("survey_cost must be positive so every mission terminates")
        if self.energy_budget < self.survey_cost + self.energy_reserve:
            raise ValueError("energy_budget cannot cover one survey and the reserve")
        if not (0 <= self.home[0] < self.height and 0 <= self.home[1] < self.width):
            raise ValueError("home is outside the grid")
        object.__setattr__(self, "home", tuple(self.home))

    def to_dict(self) -> dict:
        return asdict(self)


def load_config(path: str | Path = "config.yaml") -> SimConfig:
    with open(path, encoding="utf-8") as handle:
        return SimConfig(**(yaml.safe_load(handle) or {}))
