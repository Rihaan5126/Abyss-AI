"""Travel graph and robot state. This is mission planning, not a motion controller."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from .contract import Cell

# Half of the 8-neighbourhood: each undirected edge is added once, then mirrored.
_NEIGHBOUR_OFFSETS = ((0, 1), (1, 0), (1, 1), (1, -1))


class TravelGraph:
    """Eight-connected grid. Edge cost = distance * (1 + factor * |depth change| / depth std).

    Costs are symmetric, so the cost home from any cell is one Dijkstra run from home.
    """

    def __init__(self, depth_m: np.ndarray, terrain_cost_factor: float) -> None:
        self.shape = depth_m.shape
        height, width = self.shape
        scale = depth_m.std() or 1.0
        sources, targets, costs = [], [], []
        for d_row, d_col in _NEIGHBOUR_OFFSETS:
            for row in range(height):
                for col in range(width):
                    n_row, n_col = row + d_row, col + d_col
                    if not (0 <= n_row < height and 0 <= n_col < width):
                        continue
                    distance = float(np.hypot(d_row, d_col))
                    climb = abs(depth_m[row, col] - depth_m[n_row, n_col]) / scale
                    sources.append(self._index((row, col)))
                    targets.append(self._index((n_row, n_col)))
                    costs.append(distance * (1.0 + terrain_cost_factor * climb))
        n_cells = height * width
        self._graph = csr_matrix(
            (costs + costs, (sources + targets, targets + sources)), shape=(n_cells, n_cells)
        )

    def _index(self, cell: Cell) -> int:
        return cell[0] * self.shape[1] + cell[1]

    def _cell(self, index: int) -> Cell:
        row, col = np.unravel_index(index, self.shape)
        return int(row), int(col)

    def costs_from(self, cell: Cell) -> tuple[np.ndarray, np.ndarray]:
        """Return (cost grid, predecessors) for shortest paths from ``cell``."""
        distances, predecessors = dijkstra(
            self._graph, indices=self._index(cell), return_predecessors=True
        )
        return distances.reshape(self.shape), predecessors

    def route(self, predecessors: np.ndarray, start: Cell, target: Cell) -> tuple[Cell, ...]:
        """Cells from ``start`` to ``target``, inclusive."""
        path = [self._index(target)]
        start_index = self._index(start)
        while path[-1] != start_index:
            path.append(int(predecessors[path[-1]]))
        return tuple(self._cell(index) for index in reversed(path))


@dataclass
class RobotState:
    """Mutable vehicle state, owned by the simulator."""

    position: Cell
    energy_remaining: float
    energy_used: float = 0.0
    discovered: list[str] = field(default_factory=list)

    def spend(self, amount: float) -> None:
        self.energy_remaining -= amount
        self.energy_used += amount
