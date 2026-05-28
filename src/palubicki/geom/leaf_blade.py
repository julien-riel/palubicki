"""Parametric leaf blade generation.

Per-shape outline functions return a 2D boundary polygon + interior anchor;
a shared margin pass perturbs the boundary with teeth or lobes; a fan-from-
anchor triangulator emits triangles; the result is lifted into a flat 3D
primitive aligned with given basis vectors (done in geom/leaves.py).

Conventions:
    - 2D local frame: (u, v). u = lateral, v = blade-length axis.
    - Origin (0, 0) is the petiole attachment point.
    - Boundary points are CCW, do NOT include a duplicate closing vertex.
    - Anchor is interior to the polygon; star-shape from anchor is required.
"""
from __future__ import annotations

from typing import Literal

import numpy as np

Shape = Literal["linear", "elliptic", "lanceolate", "ovate", "cordate", "palmate"]
Margin = Literal["entire", "serrate", "dentate", "lobed"]

_SHAPES = ("linear", "elliptic", "lanceolate", "ovate", "cordate", "palmate")
_MARGINS = ("entire", "serrate", "dentate", "lobed")


def build_blade(
    *,
    length: float,
    width: float,
    shape: str,
    margin: str,
    margin_depth: float = 0.0,
    margin_count: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build a triangulated leaf blade as a flat 3D mesh in the (u, v, 0) plane.

    Returns
    -------
    positions : (N, 3) float32
        Vertex positions. positions[0] is the anchor; positions[1:] are the
        boundary points after margin modulation.
    normals : (N, 3) float32
        Constant +z normal for all vertices.
    uvs : (N, 2) float32
        tex_u = (u + width/2) / width, tex_v = v / length.
    indices : (M,) uint32
        Triangle indices; M is divisible by 3.
    """
    if length <= 0:
        raise ValueError(f"length must be > 0, got {length}")
    if width <= 0:
        raise ValueError(f"width must be > 0, got {width}")
    if not (0.0 <= margin_depth <= 1.0):
        raise ValueError(f"margin_depth must be in [0, 1], got {margin_depth}")
    if margin_count < 0:
        raise ValueError(f"margin_count must be >= 0, got {margin_count}")
    if shape not in _SHAPES:
        raise ValueError(
            f"unknown leaf shape: {shape!r}; expected one of {list(_SHAPES)}"
        )
    if margin not in _MARGINS:
        raise ValueError(
            f"unknown leaf margin: {margin!r}; expected one of {list(_MARGINS)}"
        )

    outline_fn = _OUTLINE_FNS[shape]
    boundary, anchor = outline_fn(length, width)
    # margin pass (no-op for "entire" or count==0)
    boundary = _apply_margin(boundary, margin, margin_depth, margin_count, shape, length, width)
    positions_2d, indices = _triangulate_fan(boundary, anchor)

    # Lift 2D into 3D: z=0, normal=+z, UV from bounding-box convention.
    n = positions_2d.shape[0]
    positions = np.zeros((n, 3), dtype=np.float32)
    positions[:, 0] = positions_2d[:, 0]
    positions[:, 1] = positions_2d[:, 1]
    normals = np.zeros((n, 3), dtype=np.float32)
    normals[:, 2] = 1.0
    uvs = np.empty((n, 2), dtype=np.float32)
    uvs[:, 0] = (positions_2d[:, 0] + width * 0.5) / width
    uvs[:, 1] = positions_2d[:, 1] / length
    indices = indices.astype(np.uint32, copy=False)
    return positions, normals, uvs, indices


def _outline_linear(L: float, W: float) -> tuple[np.ndarray, np.ndarray]:
    boundary = np.array(
        [[-W * 0.5, 0.0], [W * 0.5, 0.0], [W * 0.5, L], [-W * 0.5, L]],
        dtype=np.float64,
    )
    anchor = np.array([0.0, L * 0.5], dtype=np.float64)
    return boundary, anchor


def _outline_elliptic(L: float, W: float, n: int = 16) -> tuple[np.ndarray, np.ndarray]:
    """Half-ellipse symmetric about u=0, max width at v=L/2."""
    # Sample boundary CCW starting from petiole (0, 0).
    # Right side ascending: v from 0 to L; left side descending: v from L to 0.
    # Use n samples per side; skip duplicate at petiole and tip.
    half = max(2, n // 2)
    t_right = np.linspace(0.0, 1.0, half, endpoint=False)
    v_right = t_right * L
    u_right = (W * 0.5) * np.sin(np.pi * t_right)
    t_left = np.linspace(1.0, 0.0, half, endpoint=False)
    v_left = t_left * L
    u_left = -(W * 0.5) * np.sin(np.pi * t_left)
    boundary = np.empty((2 * half, 2), dtype=np.float64)
    boundary[:half, 0] = u_right
    boundary[:half, 1] = v_right
    boundary[half:, 0] = u_left
    boundary[half:, 1] = v_left
    anchor = np.array([0.0, L * 0.5], dtype=np.float64)
    return boundary, anchor


def _outline_lanceolate(L: float, W: float, n: int = 16) -> tuple[np.ndarray, np.ndarray]:
    """Widest at v≈2L/5, narrow at both ends (asymmetrically tapered)."""
    half = max(2, n // 2)
    t_right = np.linspace(0.0, 1.0, half, endpoint=False)
    v_right = t_right * L
    # sin(pi * t^0.7): peak at t = 0.5^(1/0.7) ≈ 0.37, giving widest at v ≈ 0.37L.
    u_right = (W * 0.5) * np.sin(np.pi * np.power(t_right, 0.7))
    t_left = np.linspace(1.0, 0.0, half, endpoint=False)
    v_left = t_left * L
    u_left = -(W * 0.5) * np.sin(np.pi * np.power(t_left, 0.7))
    boundary = np.empty((2 * half, 2), dtype=np.float64)
    boundary[:half, 0] = u_right
    boundary[:half, 1] = v_right
    boundary[half:, 0] = u_left
    boundary[half:, 1] = v_left
    anchor = np.array([0.0, L / 3.0], dtype=np.float64)
    return boundary, anchor


def _outline_ovate(L: float, W: float, n: int = 16) -> tuple[np.ndarray, np.ndarray]:
    """Broadly widened near the base, widest at v≈L/4, tapering toward tip."""
    half = max(2, n // 2)
    t_right = np.linspace(0.0, 1.0, half, endpoint=False)
    v_right = t_right * L
    # sin(pi * t^0.5): peak at t = 0.5^(1/0.5) = 0.25, giving widest at v ≈ 0.25L.
    # Broader at the base than lanceolate (which peaks later at v ≈ 0.37L).
    u_right = (W * 0.5) * np.sin(np.pi * np.power(t_right, 0.5))
    t_left = np.linspace(1.0, 0.0, half, endpoint=False)
    v_left = t_left * L
    u_left = -(W * 0.5) * np.sin(np.pi * np.power(t_left, 0.5))
    boundary = np.empty((2 * half, 2), dtype=np.float64)
    boundary[:half, 0] = u_right
    boundary[:half, 1] = v_right
    boundary[half:, 0] = u_left
    boundary[half:, 1] = v_left
    anchor = np.array([0.0, L / 3.0], dtype=np.float64)
    return boundary, anchor


def _outline_cordate(L: float, W: float, n: int = 20) -> tuple[np.ndarray, np.ndarray]:
    """Heart-shaped: ovate body with a basal notch below v=0."""
    # CCW winding: right side ascends (v: 0→L), left side descends (v: L→0),
    # then a notch vertex dips below the petiole, closing the loop.
    # Notch at the end means it sits between the left tail (near v=0) and the
    # right start (v=0), so it never interrupts the main body traversal.
    half = max(3, n // 2)
    t_right = np.linspace(0.0, 1.0, half, endpoint=False)
    v_right = t_right * L
    u_right = (W * 0.5) * np.power(np.sin(np.pi * t_right), 1.0) \
              * (1.0 - 0.4 * t_right)
    t_left = np.linspace(1.0, 0.0, half, endpoint=False)
    v_left = t_left * L
    u_left = -(W * 0.5) * np.power(np.sin(np.pi * t_left), 1.0) \
              * (1.0 - 0.4 * t_left)
    # Notch vertex placed AFTER the left side (left tail ends near v≈0),
    # before wrapping back to the right start at v=0.
    boundary = np.empty((2 * half + 1, 2), dtype=np.float64)
    boundary[:half, 0] = u_right
    boundary[:half, 1] = v_right
    boundary[half:half + half, 0] = u_left
    boundary[half:half + half, 1] = v_left
    # Notch dips below the petiole at the closure point
    boundary[2 * half, 0] = 0.0
    boundary[2 * half, 1] = -L / 8.0
    anchor = np.array([0.0, L / 3.0], dtype=np.float64)
    return boundary, anchor


def _triangulate_fan(
    boundary: np.ndarray, anchor: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Fan triangulate boundary from anchor. positions[0] is the anchor."""
    n = boundary.shape[0]
    positions = np.empty((n + 1, 2), dtype=np.float64)
    positions[0] = anchor
    positions[1:] = boundary
    indices = np.empty((n * 3,), dtype=np.uint32)
    for i in range(n):
        indices[3 * i + 0] = 0
        indices[3 * i + 1] = 1 + i
        indices[3 * i + 2] = 1 + ((i + 1) % n)
    return positions, indices


def _apply_margin(
    boundary: np.ndarray, margin: str, depth: float, count: int,
    shape: str, length: float, width: float,
) -> np.ndarray:
    """No-op for now; subsequent task implements serrate/dentate/lobed."""
    if margin == "entire" or count == 0:
        return boundary
    return boundary  # placeholder; later task adds tooth insertion


_OUTLINE_FNS = {
    "linear": _outline_linear,
    "elliptic": _outline_elliptic,
    "lanceolate": _outline_lanceolate,
    "ovate": _outline_ovate,
    "cordate": _outline_cordate,
}
