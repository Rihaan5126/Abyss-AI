"""Planner registry. Add new policies here so the mission runner can find them."""

from .adaptive import AdaptivePlanner, NoInfoPlanner, NoLearnPlanner
from .base import Planner
from .discovery import (
    DiscoveryPlanner, DiscoveryNoLearnPlanner, DiscoveryNoRarityPlanner,
    DiscoveryNoLookaheadPlanner, DiscoveryNoWarmupPlanner, DiscoveryNoVisionGuardPlanner, DiscoveryRoutePlanner,
)
from .frontier import FrontierPlanner
from .heuristic import TerrainHeuristicPlanner
from .lawnmower import LawnmowerPlanner
from .novelty import NoveltyPlanner
from .random import RandomPlanner

PLANNERS: dict[str, type[Planner]] = {
    cls.name: cls
    for cls in (
        RandomPlanner,
        AdaptivePlanner,
        NoLearnPlanner,
        NoInfoPlanner,
        NoveltyPlanner,
        DiscoveryPlanner,
        DiscoveryNoLearnPlanner,
        DiscoveryNoRarityPlanner,
        DiscoveryNoLookaheadPlanner,
        DiscoveryNoWarmupPlanner,
        DiscoveryRoutePlanner,
        DiscoveryNoVisionGuardPlanner,
        FrontierPlanner,
        TerrainHeuristicPlanner,
        LawnmowerPlanner,
    )
}

PLANNER_LABELS = {
    "abyss": "ABYSS",
    "abyss-discovery": "ABYSS Discovery (experimental)",
    "abyss-discovery-nolearn": "Discovery: no learning",
    "abyss-discovery-norarity": "Discovery: no rarity weighting",
    "abyss-discovery-myopic": "Discovery: one stop",
    "abyss-discovery-nowarmup": "Discovery: no initial sampling",
    "abyss-discovery-route": "Discovery: three-stop routes",
    "abyss-discovery-unguarded": "Discovery: unguarded vision",
}
