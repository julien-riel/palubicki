# src/palubicki/sim/markers.py
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree


class MarkerCloud:
    """All markers as a fixed positions array + alive mask + lazy KDTree."""

    def __init__(self, positions: np.ndarray) -> None:
        self._positions = np.asarray(positions, dtype=np.float64)
        self._alive = np.ones(len(self._positions), dtype=bool)
        self._tree: cKDTree | None = None
        self._tree_alive_indices: np.ndarray | None = None

    @property
    def alive_count(self) -> int:
        return int(self._alive.sum())

    def alive_positions(self) -> np.ndarray:
        return self._positions[self._alive]

    def positions_for(self, indices: np.ndarray) -> np.ndarray:
        """Return positions for the given marker indices (original index space)."""
        return self._positions[np.asarray(indices, dtype=np.intp)]

    def _ensure_tree(self) -> None:
        if self._tree is not None:
            return
        alive_idx = np.flatnonzero(self._alive)
        self._tree_alive_indices = alive_idx
        if len(alive_idx) == 0:
            self._tree = cKDTree(np.zeros((1, 3)))
        else:
            self._tree = cKDTree(self._positions[alive_idx])

    def query_radius(self, point: np.ndarray, r: float) -> np.ndarray:
        """Return ORIGINAL indices of alive markers within radius r of point."""
        self._ensure_tree()
        if len(self._tree_alive_indices) == 0:
            return np.array([], dtype=np.intp)
        local_idx = self._tree.query_ball_point(point, r)
        return self._tree_alive_indices[np.asarray(local_idx, dtype=np.intp)]

    def query_radius_batch(self, points: np.ndarray, r: float) -> list[np.ndarray]:
        """Batched query: list of ORIGINAL alive-marker indices, one entry per query point.

        Preserves per-point ordering identical to a sequence of query_radius() calls so
        downstream insertion-order-dependent code (perceive pass 2) stays bit-exact.
        """
        self._ensure_tree()
        if len(self._tree_alive_indices) == 0:
            return [np.array([], dtype=np.intp) for _ in range(len(points))]
        local_lists = self._tree.query_ball_point(np.asarray(points, dtype=np.float64), r)
        alive = self._tree_alive_indices
        return [alive[np.asarray(lst, dtype=np.intp)] for lst in local_lists]

    def kill_near(self, points: np.ndarray, kill_radius: float) -> None:
        """Mark all alive markers within kill_radius of any point as dead. Rebuild tree."""
        if self.alive_count == 0 or len(points) == 0:
            return
        self._ensure_tree()
        local_idx_lists = self._tree.query_ball_point(points, kill_radius)
        to_kill_local: set[int] = set()
        for lst in local_idx_lists:
            to_kill_local.update(lst)
        if to_kill_local:
            original = self._tree_alive_indices[np.fromiter(to_kill_local, dtype=np.intp)]
            self._alive[original] = False
            self._tree = None
            self._tree_alive_indices = None
