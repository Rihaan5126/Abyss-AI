"""Planner registry. Add new policies here so the mission runner can find them."""

from .base import Planner
from .random import RandomPlanner

PLANNERS: dict[str, type[Planner]] = {
    RandomPlanner.name: RandomPlanner,
}
