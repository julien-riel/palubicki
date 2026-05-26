# src/palubicki/sim/obstacles.py
from __future__ import annotations

from typing import Protocol

import numpy as np

from palubicki.config import ObstacleAABB, ObstacleSphere, ObstacleOBB

LAI_OPAQUE: float = 1e6


class Obstacle(Protocol):
    def contains(self, points: np.ndarray) -> np.ndarray: ...
    def segment_intersects(self, p0: np.ndarray, p1: np.ndarray) -> bool: ...
    def aabb(self) -> tuple[np.ndarray, np.ndarray]: ...
    def voxelize(self, grid) -> np.ndarray: ...


class AABBObstacle:
    def __init__(self, cfg: ObstacleAABB):
        self._min = np.asarray(cfg.min, dtype=np.float64)
        self._max = np.asarray(cfg.max, dtype=np.float64)

    def contains(self, points: np.ndarray) -> np.ndarray:
        pts = np.asarray(points, dtype=np.float64)
        if pts.shape[0] == 0:
            return np.zeros(0, dtype=bool)
        return np.all((pts >= self._min) & (pts <= self._max), axis=1)

    def segment_intersects(self, p0: np.ndarray, p1: np.ndarray) -> bool:
        p0 = np.asarray(p0, dtype=np.float64)
        p1 = np.asarray(p1, dtype=np.float64)
        d = p1 - p0
        t_enter = 0.0
        t_exit = 1.0
        for axis in range(3):
            if abs(d[axis]) < 1e-12:
                if p0[axis] < self._min[axis] or p0[axis] > self._max[axis]:
                    return False
                continue
            inv = 1.0 / d[axis]
            t1 = (self._min[axis] - p0[axis]) * inv
            t2 = (self._max[axis] - p0[axis]) * inv
            t_lo, t_hi = (t1, t2) if t1 <= t2 else (t2, t1)
            t_enter = max(t_enter, t_lo)
            t_exit = min(t_exit, t_hi)
            if t_enter > t_exit:
                return False
        return bool(t_enter <= t_exit)

    def aabb(self) -> tuple[np.ndarray, np.ndarray]:
        return self._min.copy(), self._max.copy()

    def voxelize(self, grid) -> np.ndarray:
        # Implemented in Task 13.
        raise NotImplementedError("voxelize: implemented in Task 13")


class SphereObstacle:
    def __init__(self, cfg: ObstacleSphere):
        self._center = np.asarray(cfg.center, dtype=np.float64)
        self._radius = float(cfg.radius)
        self._r2 = self._radius * self._radius

    def contains(self, points: np.ndarray) -> np.ndarray:
        pts = np.asarray(points, dtype=np.float64)
        if pts.shape[0] == 0:
            return np.zeros(0, dtype=bool)
        delta = pts - self._center
        return np.einsum("ij,ij->i", delta, delta) <= self._r2

    def segment_intersects(self, p0: np.ndarray, p1: np.ndarray) -> bool:
        p0 = np.asarray(p0, dtype=np.float64)
        p1 = np.asarray(p1, dtype=np.float64)
        d = p1 - p0
        f = p0 - self._center
        a = float(np.dot(d, d))
        if a < 1e-24:
            return float(np.dot(f, f)) <= self._r2
        b = 2.0 * float(np.dot(f, d))
        c = float(np.dot(f, f)) - self._r2
        disc = b * b - 4.0 * a * c
        if disc < 0:
            return False
        sqrt_disc = float(np.sqrt(disc))
        t1 = (-b - sqrt_disc) / (2.0 * a)
        t2 = (-b + sqrt_disc) / (2.0 * a)
        # Segment intersects iff [t1, t2] overlaps [0, 1]
        return t2 >= 0.0 and t1 <= 1.0

    def aabb(self) -> tuple[np.ndarray, np.ndarray]:
        r = np.array([self._radius, self._radius, self._radius])
        return self._center - r, self._center + r

    def voxelize(self, grid) -> np.ndarray:
        raise NotImplementedError("voxelize: implemented in Task 13")


class OBBObstacle:
    """Oriented box. `axes` is a row-major 3x3 orthonormal rotation matrix R that
    maps WORLD vectors to LOCAL (point_local = R @ (point_world - center)). A point
    is inside iff |local[i]| <= half_extents[i] for all i."""

    def __init__(self, cfg: ObstacleOBB):
        self._center = np.asarray(cfg.center, dtype=np.float64)
        self._half = np.asarray(cfg.half_extents, dtype=np.float64)
        self._R = np.asarray(cfg.axes, dtype=np.float64).reshape(3, 3)

    def _to_local(self, pts: np.ndarray) -> np.ndarray:
        return (pts - self._center) @ self._R.T

    def contains(self, points: np.ndarray) -> np.ndarray:
        pts = np.asarray(points, dtype=np.float64)
        if pts.shape[0] == 0:
            return np.zeros(0, dtype=bool)
        local = self._to_local(pts)
        return np.all(np.abs(local) <= self._half, axis=1)

    def segment_intersects(self, p0: np.ndarray, p1: np.ndarray) -> bool:
        # Transform segment into local frame, then slab test against [-half, +half]
        p0_l = self._to_local(np.asarray(p0, dtype=np.float64).reshape(1, 3))[0]
        p1_l = self._to_local(np.asarray(p1, dtype=np.float64).reshape(1, 3))[0]
        d = p1_l - p0_l
        t_enter = 0.0
        t_exit = 1.0
        for axis in range(3):
            if abs(d[axis]) < 1e-12:
                if p0_l[axis] < -self._half[axis] or p0_l[axis] > self._half[axis]:
                    return False
                continue
            inv = 1.0 / d[axis]
            t1 = (-self._half[axis] - p0_l[axis]) * inv
            t2 = (self._half[axis] - p0_l[axis]) * inv
            t_lo, t_hi = (t1, t2) if t1 <= t2 else (t2, t1)
            t_enter = max(t_enter, t_lo)
            t_exit = min(t_exit, t_hi)
            if t_enter > t_exit:
                return False
        return bool(t_enter <= t_exit)

    def aabb(self) -> tuple[np.ndarray, np.ndarray]:
        # World AABB = center ± |R^T| @ half_extents (extent of all 8 corners projected
        # to world axes equals sum of |R^T_ij| * half_extents_j for each world axis i).
        extent = np.abs(self._R.T) @ self._half
        return self._center - extent, self._center + extent

    def voxelize(self, grid) -> np.ndarray:
        raise NotImplementedError("voxelize: implemented in Task 13")
