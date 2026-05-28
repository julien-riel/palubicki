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


def _outline_palmate(L: float, W: float, samples_per_lobe: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """5 radial lobes from center (0, 0.4*L).

    Each lobe has a peak at angle theta_k and an inter-lobe valley at the
    midpoint between adjacent peaks. Boundary is sampled around the polar
    contour at samples_per_lobe samples per lobe (lobe edge from valley → peak
    → valley = 2 segments) plus extra detail at peaks.
    """
    n_lobes = 5
    cx, cy = 0.0, 0.4 * L
    anchor = np.array([cx, cy], dtype=np.float64)
    R_peak = 0.5 * max(L, W)
    R_valley = 0.3 * R_peak
    # Lobe peak angles (radians); CCW around the center starting at pi/2 (straight up).
    # IMPORTANT: theta_next_peak intentionally does NOT modulo by n_lobes — the
    # last lobe's valley needs to be at theta+2pi/5, not wrap back to pi/2.
    boundary_pts = []
    for k in range(n_lobes):
        theta_peak = np.pi * 0.5 + k * (2.0 * np.pi / n_lobes)
        theta_next_peak = np.pi * 0.5 + (k + 1) * (2.0 * np.pi / n_lobes)
        # Emit the peak itself.
        peak = np.array([cx + R_peak * np.cos(theta_peak),
                         cy + R_peak * np.sin(theta_peak)])
        boundary_pts.append(peak)
        # Walk from peak to inter-lobe valley with intermediate samples.
        theta_valley = (theta_peak + theta_next_peak) * 0.5
        for s in range(1, samples_per_lobe):
            t = s / samples_per_lobe
            theta = theta_peak + t * (theta_valley - theta_peak)
            R = R_peak + t * (R_valley - R_peak)
            boundary_pts.append(np.array([cx + R * np.cos(theta),
                                          cy + R * np.sin(theta)]))
        # Emit the valley.
        boundary_pts.append(np.array([cx + R_valley * np.cos(theta_valley),
                                      cy + R_valley * np.sin(theta_valley)]))
        # Walk from valley to the NEXT peak with intermediate samples.
        for s in range(1, samples_per_lobe):
            t = s / samples_per_lobe
            theta = theta_valley + t * (theta_next_peak - theta_valley)
            R = R_valley + t * (R_peak - R_valley)
            boundary_pts.append(np.array([cx + R * np.cos(theta),
                                          cy + R * np.sin(theta)]))
    boundary = np.array(boundary_pts, dtype=np.float64)
    # Defensive CCW check; reverse if signed area came out negative.
    x = boundary[:, 0]
    y = boundary[:, 1]
    area = 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
    if area < 0:
        boundary = boundary[::-1].copy()
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


_MARGIN_PARAMS = {
    # (peak_offset_fraction_of_period, valley_pull_factor)
    # peak_offset > 0 = forward (toward apex/tip-end)
    "serrate": (0.5, 1.0),
    "dentate": (0.0, 0.5),
    "lobed": (0.0, 1.0),
}


def _apply_margin(
    boundary: np.ndarray, margin: str, depth: float, count: int,
    shape: str, length: float, width: float,
) -> np.ndarray:
    """Insert 2*count tooth vertices (valley, peak) along the boundary.

    Teeth are spaced evenly by arc length over the *eligible* arc (excluding
    the petiole stub for symmetric shapes, the notch for cordate). For each
    tooth midpoint:
        valley  = P + n_in * (depth * w_local)
        peak    = P - n_in * (depth * w_local) + tan * (peak_offset * period)
    where n_in is the inward unit normal, tan the unit tangent at P, w_local
    a shape-aware radius scale, and period the spacing between consecutive
    teeth measured in arc length.
    """
    if margin == "entire" or count == 0:
        return boundary
    if margin not in _MARGIN_PARAMS:
        raise ValueError(f"unknown leaf margin: {margin!r}")
    peak_off_frac, valley_pull = _MARGIN_PARAMS[margin]

    n = boundary.shape[0]
    # Arc lengths between consecutive boundary points (with wraparound).
    diffs = np.diff(boundary, axis=0, append=boundary[:1])
    seg_lens = np.linalg.norm(diffs, axis=1)
    cum = np.concatenate(([0.0], np.cumsum(seg_lens)))
    total_arc = cum[-1]

    # Eligible arc: skip a small petiole stub near v=0 for symmetric shapes
    # and the basal notch for cordate. For palmate, every lobe edge counts.
    eligible_start, eligible_end = _eligible_arc_range(shape, boundary, cum, total_arc)
    eligible_length = eligible_end - eligible_start
    if eligible_length <= 0:
        return boundary

    # Tooth positions evenly spaced over eligible arc.
    # Place midpoints at fractional positions (k + 0.5) / count, k = 0..count-1.
    positions_arc = eligible_start + (np.arange(count) + 0.5) * (eligible_length / count)
    period = eligible_length / count

    # Build the new boundary by walking boundary segments and inserting teeth
    # at the right arc positions.
    out: list[np.ndarray] = []
    tooth_idx = 0
    for i in range(n):
        out.append(boundary[i])
        # Check if any teeth fall in segment [cum[i], cum[i+1]].
        while tooth_idx < count and cum[i] <= positions_arc[tooth_idx] < cum[i + 1]:
            arc_pos = positions_arc[tooth_idx]
            t = (arc_pos - cum[i]) / max(seg_lens[i], 1e-12)
            P = boundary[i] + t * diffs[i]
            tan = diffs[i] / max(seg_lens[i], 1e-12)
            # Ensure tangent points toward apex (positive v) for consistent
            # "forward" direction used by serrate peak offsets.
            apex_tan = tan if tan[1] >= 0 else -tan
            n_in = np.array([-tan[1], tan[0]])  # left-hand normal; CCW interior = left
            # Make sure n_in points inward: compare to vector from P to centroid.
            centroid = boundary.mean(axis=0)
            if np.dot(n_in, centroid - P) < 0:
                n_in = -n_in
            # Local width: use radial distance from centroid to P.
            w_local = float(np.linalg.norm(P - centroid))
            valley_pull_amt = depth * w_local * valley_pull
            peak_push_amt = depth * w_local
            peak_tangent_offset = peak_off_frac * period
            valley = P + n_in * valley_pull_amt
            peak = P - n_in * peak_push_amt + apex_tan * peak_tangent_offset
            out.append(valley)
            out.append(peak)
            tooth_idx += 1
    return np.array(out, dtype=np.float64)


def _eligible_arc_range(
    shape: str, boundary: np.ndarray, cum: np.ndarray, total_arc: float
) -> tuple[float, float]:
    """Skip the petiole stub for symmetric shapes; include everything else.

    For symmetric shapes (linear/elliptic/lanceolate/ovate), the petiole is
    the segment crossing y≈0 at the very start of the boundary. We skip the
    first and last 2% of the total arc to avoid placing teeth at the petiole.
    For cordate, the basal notch is included in that skip range. For palmate,
    every arc point is eligible.
    """
    if shape == "palmate":
        return 0.0, total_arc
    skip = 0.02 * total_arc
    return skip, total_arc - skip


_OUTLINE_FNS = {
    "linear": _outline_linear,
    "elliptic": _outline_elliptic,
    "lanceolate": _outline_lanceolate,
    "ovate": _outline_ovate,
    "cordate": _outline_cordate,
    "palmate": _outline_palmate,
}
