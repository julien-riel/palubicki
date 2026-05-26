# src/palubicki/sim/obstacles.py
from __future__ import annotations

from typing import Protocol

import numpy as np

from palubicki.config import ObstacleAABB, ObstacleSphere, ObstacleOBB, ObstacleMesh

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


class MeshObstacle:
    """Wraps a trimesh.Trimesh. Supports translate + uniform scale (applied at load).
    Uses trimesh.contains for point-in-mesh and ray casting for segment intersection."""

    def __init__(self, cfg: ObstacleMesh):
        import trimesh
        mesh = trimesh.load(str(cfg.path), force="mesh")
        if not isinstance(mesh, trimesh.Trimesh):
            raise ValueError(f"path {cfg.path} did not load as a single Trimesh")
        mesh = mesh.copy()
        if cfg.scale != 1.0:
            mesh.apply_scale(cfg.scale)
        if cfg.translate != (0.0, 0.0, 0.0):
            mesh.apply_translation(np.asarray(cfg.translate, dtype=np.float64))
        self._mesh = mesh
        self._ray = trimesh.ray.ray_triangle.RayMeshIntersector(mesh)

    def contains(self, points: np.ndarray) -> np.ndarray:
        pts = np.asarray(points, dtype=np.float64)
        if pts.shape[0] == 0:
            return np.zeros(0, dtype=bool)
        return self._mesh.contains(pts)

    def segment_intersects(self, p0: np.ndarray, p1: np.ndarray) -> bool:
        p0 = np.asarray(p0, dtype=np.float64)
        p1 = np.asarray(p1, dtype=np.float64)
        # Endpoint-inside test (cheap; covers buds-already-inside cases)
        if bool(self._mesh.contains(p0.reshape(1, 3))[0]) or bool(self._mesh.contains(p1.reshape(1, 3))[0]):
            return True
        d = p1 - p0
        seg_len = float(np.linalg.norm(d))
        if seg_len < 1e-12:
            return False
        direction = d / seg_len
        locations, _, _ = self._ray.intersects_location(
            ray_origins=p0.reshape(1, 3),
            ray_directions=direction.reshape(1, 3),
            multiple_hits=False,
        )
        if len(locations) == 0:
            return False
        # Distance from p0 to the first hit
        dist = float(np.linalg.norm(locations[0] - p0))
        return dist <= seg_len

    def aabb(self) -> tuple[np.ndarray, np.ndarray]:
        bb = self._mesh.bounds   # (2, 3): [[xmin, ymin, zmin], [xmax, ymax, zmax]]
        return bb[0].astype(np.float64), bb[1].astype(np.float64)

    def voxelize(self, grid) -> np.ndarray:
        raise NotImplementedError("voxelize: implemented in Task 13")

    @property
    def trimesh(self):
        return self._mesh


def build_obstacles(cfg) -> list:
    """Instantiate concrete obstacles from ForestConfig.obstacles."""
    out = []
    for entry in cfg.obstacles:
        if isinstance(entry, ObstacleAABB):
            out.append(AABBObstacle(entry))
        elif isinstance(entry, ObstacleSphere):
            out.append(SphereObstacle(entry))
        elif isinstance(entry, ObstacleOBB):
            out.append(OBBObstacle(entry))
        elif isinstance(entry, ObstacleMesh):
            out.append(MeshObstacle(entry))
        else:
            raise TypeError(f"unknown obstacle config type: {type(entry).__name__}")
    return out


def filter_markers(positions: np.ndarray, obstacles: list) -> np.ndarray:
    """Drop positions that fall inside any obstacle."""
    if len(obstacles) == 0 or len(positions) == 0:
        return positions
    keep = np.ones(len(positions), dtype=bool)
    for o in obstacles:
        keep &= ~o.contains(positions)
    return positions[keep]


def segment_blocked(p0: np.ndarray, p1: np.ndarray, obstacles: list) -> bool:
    """True iff any obstacle blocks the segment [p0, p1]."""
    for o in obstacles:
        if o.segment_intersects(p0, p1):
            return True
    return False


def any_contains(point: np.ndarray, obstacles: list) -> bool:
    """True iff `point` lies inside any obstacle."""
    if len(obstacles) == 0:
        return False
    pts = np.asarray(point, dtype=np.float64).reshape(1, 3)
    for o in obstacles:
        if bool(o.contains(pts)[0]):
            return True
    return False
