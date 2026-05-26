# src/palubicki/render/renderer.py
from __future__ import annotations

import numpy as np

from palubicki.geom.mesh import Mesh


def _flatten(mesh: Mesh) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Concatenate all primitives into flat arrays for rendering.

    Returns:
        tri:   (T, 3, 3) float32 — T triangles, each as 3 vertices in 3D
        norm:  (T, 3)    float32 — unit-length face normal per triangle
        col:   (T, 3)    float32 — RGB face color from primitive's base_color
    """
    tris: list[np.ndarray] = []
    norms: list[np.ndarray] = []
    cols: list[np.ndarray] = []

    for p in mesh.primitives:
        idx = p.indices.reshape(-1, 3)
        # Triangle vertex positions
        tris.append(p.positions[idx].astype(np.float32, copy=False))
        # Face normal = mean of vertex normals, then renormalized
        n = p.normals[idx].astype(np.float32, copy=False).mean(axis=1)
        n /= np.linalg.norm(n, axis=1, keepdims=True).clip(1e-9)
        norms.append(n)
        # Face color = primitive's base_color broadcast to T triangles
        rgb = np.asarray(p.material.base_color[:3], dtype=np.float32)
        cols.append(np.broadcast_to(rgb, (idx.shape[0], 3)).copy())

    if not tris:
        # Empty mesh — caller should have caught this earlier.
        empty = np.zeros((0, 3, 3), dtype=np.float32)
        return empty, np.zeros((0, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.float32)

    return np.concatenate(tris), np.concatenate(norms), np.concatenate(cols)
