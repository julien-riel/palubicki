# src/palubicki/geom/obstacle_geom.py
from __future__ import annotations

import numpy as np

from palubicki.geom.mesh import Material, Primitive
from palubicki.sim.obstacles import (
    AABBObstacle, MeshObstacle, OBBObstacle, SphereObstacle,
)


def build_obstacle_primitive(obstacles: list, material: Material) -> Primitive | None:
    if not obstacles:
        return None

    all_pos: list[np.ndarray] = []
    all_norm: list[np.ndarray] = []
    all_uv: list[np.ndarray] = []
    all_idx: list[np.ndarray] = []
    vertex_offset = 0

    for o in obstacles:
        pos, norm, uv, idx = _triangulate(o)
        all_pos.append(pos)
        all_norm.append(norm)
        all_uv.append(uv)
        all_idx.append(idx + vertex_offset)
        vertex_offset += len(pos)

    return Primitive(
        positions=np.concatenate(all_pos, axis=0).astype(np.float32),
        normals=np.concatenate(all_norm, axis=0).astype(np.float32),
        uvs=np.concatenate(all_uv, axis=0).astype(np.float32),
        indices=np.concatenate(all_idx, axis=0).astype(np.uint32),
        material=material,
    )


def _triangulate(obstacle) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if isinstance(obstacle, AABBObstacle):
        amin, amax = obstacle.aabb()
        return _box_triangles(amin, amax, R=None)
    if isinstance(obstacle, OBBObstacle):
        center = obstacle._center
        half = obstacle._half
        # R^T maps local → world; vertices in local are (±half), then transformed.
        return _box_triangles_oriented(center, half, obstacle._R.T)
    if isinstance(obstacle, SphereObstacle):
        return _uv_sphere(obstacle._center, obstacle._radius, n_lat=16, n_lon=8)
    if isinstance(obstacle, MeshObstacle):
        tm = obstacle.trimesh
        return (
            np.asarray(tm.vertices, dtype=np.float64),
            np.asarray(tm.vertex_normals, dtype=np.float64),
            np.zeros((len(tm.vertices), 2), dtype=np.float64),
            np.asarray(tm.faces, dtype=np.uint32).reshape(-1),
        )
    raise TypeError(f"unknown obstacle type: {type(obstacle).__name__}")


def _box_triangles(amin: np.ndarray, amax: np.ndarray, R: np.ndarray | None) -> tuple[np.ndarray, ...]:
    # 8 corners
    x0, y0, z0 = amin
    x1, y1, z1 = amax
    corners = np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ], dtype=np.float64)
    if R is not None:
        corners = corners @ R.T
    # 6 faces, 2 triangles each, with outward normals
    faces_idx = np.array([
        [0, 1, 2], [0, 2, 3],   # z0 face (normal -z)
        [4, 6, 5], [4, 7, 6],   # z1 face (normal +z)
        [0, 4, 5], [0, 5, 1],   # y0 face (normal -y)
        [3, 2, 6], [3, 6, 7],   # y1 face (normal +y)
        [0, 3, 7], [0, 7, 4],   # x0 face (normal -x)
        [1, 5, 6], [1, 6, 2],   # x1 face (normal +x)
    ], dtype=np.uint32).reshape(-1)
    # Per-vertex normals = approximate by averaging face normals; for a box we just
    # use a single normal pointing outward from centroid (visual debug quality).
    centroid = corners.mean(axis=0)
    normals = corners - centroid
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.where(norms > 1e-12, normals / norms, np.array([0.0, 1.0, 0.0]))
    uvs = np.zeros((len(corners), 2), dtype=np.float64)
    return corners, normals, uvs, faces_idx


def _box_triangles_oriented(center: np.ndarray, half: np.ndarray, R_local_to_world: np.ndarray):
    # Build the axis-aligned box at origin with half-extents, then rotate + translate
    amin = -half
    amax = half
    pos, norm, uv, idx = _box_triangles(amin, amax, R=R_local_to_world)
    pos = pos + center
    return pos, norm, uv, idx


def _uv_sphere(center: np.ndarray, radius: float, *, n_lat: int, n_lon: int):
    # n_lat = lon segments (around equator), n_lon = lat segments (pole to pole)
    pos: list[np.ndarray] = []
    norm: list[np.ndarray] = []
    uv: list[np.ndarray] = []
    for i in range(n_lon + 1):
        v = i / n_lon
        phi = v * np.pi
        for j in range(n_lat + 1):
            u = j / n_lat
            theta = u * 2.0 * np.pi
            n = np.array([np.sin(phi) * np.cos(theta), np.cos(phi), np.sin(phi) * np.sin(theta)])
            pos.append(center + radius * n)
            norm.append(n)
            uv.append(np.array([u, v]))
    pos_arr = np.stack(pos)
    norm_arr = np.stack(norm)
    uv_arr = np.stack(uv)
    idx: list[int] = []
    stride = n_lat + 1
    for i in range(n_lon):
        for j in range(n_lat):
            a = i * stride + j
            b = a + 1
            c = a + stride
            d = c + 1
            idx.extend([a, c, b, b, c, d])
    idx_arr = np.asarray(idx, dtype=np.uint32)
    return pos_arr, norm_arr, uv_arr, idx_arr
