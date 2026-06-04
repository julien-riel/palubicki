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

# Minimum blade half-width at the petiole (fraction of full width W), tapering
# linearly to 0 at the tip. Without it, the symmetric outlines pinch to a single
# zero-width basal vertex, so the opaque lamina "starts" off the petiole tip and
# reads as detached from the tail. The max() floor only fills the basal pinch
# region (where sin < floor); it never widens the blade past its W/2 envelope
# and leaves the apex sharp (floor → 0 at the tip).
_LEAF_BASE_HALF_WIDTH = 0.15


def build_blade(
    *,
    length: float,
    width: float,
    shape: str,
    margin: str,
    margin_depth: float = 0.0,
    margin_count: int = 0,
    subdivisions: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build a triangulated leaf blade as a flat 3D mesh in the (u, v, 0) plane.

    ``subdivisions`` > 0 inserts that many concentric interior rings between the
    anchor and the boundary, giving the lamina interior vertices for the hero
    blade (``geom/leaf_blade3d.py``) to curve smoothly across instead of a flat
    cone of slivers. 0 (default) is the legacy single fan — byte-identical, and
    the convention ``leaf_area_records`` keeps for its area integral (the
    projected polygon, hence its area, is unchanged either way).

    Returns
    -------
    positions : (N, 3) float32
        Vertex positions. positions[0] is the anchor; positions[1:] are the
        boundary points (subdivisions == 0) or the interior rings then boundary.
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
    positions_2d, indices = _triangulate_fan(boundary, anchor, subdivisions)

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
    u_right = np.maximum((W * 0.5) * np.sin(np.pi * t_right),
                         W * _LEAF_BASE_HALF_WIDTH * (1.0 - t_right))
    t_left = np.linspace(1.0, 0.0, half, endpoint=False)
    v_left = t_left * L
    u_left = -np.maximum((W * 0.5) * np.sin(np.pi * t_left),
                         W * _LEAF_BASE_HALF_WIDTH * (1.0 - t_left))
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
    u_right = np.maximum((W * 0.5) * np.sin(np.pi * np.power(t_right, 0.7)),
                         W * _LEAF_BASE_HALF_WIDTH * (1.0 - t_right))
    t_left = np.linspace(1.0, 0.0, half, endpoint=False)
    v_left = t_left * L
    u_left = -np.maximum((W * 0.5) * np.sin(np.pi * np.power(t_left, 0.7)),
                         W * _LEAF_BASE_HALF_WIDTH * (1.0 - t_left))
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
    u_right = np.maximum((W * 0.5) * np.sin(np.pi * np.power(t_right, 0.5)),
                         W * _LEAF_BASE_HALF_WIDTH * (1.0 - t_right))
    t_left = np.linspace(1.0, 0.0, half, endpoint=False)
    v_left = t_left * L
    u_left = -np.maximum((W * 0.5) * np.sin(np.pi * np.power(t_left, 0.5)),
                         W * _LEAF_BASE_HALF_WIDTH * (1.0 - t_left))
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


_PALMATE_LOBES = 5


def _palmate_fan(L: float, W: float) -> tuple[float, float, list[float], list[float]]:
    """Shared palmate fan parameters in the 2D (u, v) blade frame.

    Returns ``(cx, cy, peak_angles, peak_radii)``: the radiating centre just above
    the petiole tip and, per lobe, the polar angle + radius of its apex. The lobes
    fan over an upward ~150° arc; the central lobe is longest (rounded fan); each
    reach is capped to the [-W/2, W/2] x [0, L] box so the UV stays on-atlas. The
    single source of truth consumed by :func:`_outline_palmate` (mesh outline) and
    :func:`palmate_lobe_axes` (texture + 3D relief), so they cannot drift.
    """
    n_lobes = _PALMATE_LOBES
    cx, cy = 0.0, 0.08 * L
    up = np.pi * 0.5                       # +v, toward the tip
    fan_half = np.radians(74.0)            # half of the ~150° upward fan
    half_w, top_v = 0.49 * W, 0.97 * L

    def reach(theta: float) -> float:
        """Max radius from (cx, cy) at ``theta`` before leaving the UV box."""
        c, s = np.cos(theta), np.sin(theta)
        lims = []
        if abs(c) > 1e-6:
            lims.append(half_w / abs(c))
        if s > 1e-6:
            lims.append((top_v - cy) / s)
        return float(min(lims)) if lims else (top_v - cy)

    peak_angles = [(up - fan_half) + (2.0 * fan_half) * (k / (n_lobes - 1))
                   for k in range(n_lobes)]
    # Central lobe fills ~0.97 of its reach; outer lobes shorter → rounded fan.
    peak_radii = [(0.72 + 0.25 * np.sin(np.pi * (k / (n_lobes - 1)))) * reach(peak_angles[k])
                  for k in range(n_lobes)]
    return cx, cy, peak_angles, peak_radii


def palmate_lobe_axes(L: float = 1.0, W: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """The palmate venation skeleton: the fan anchor + the lobe-tip points, in the
    2D (u, v) blade frame (origin = petiole attachment, v = base→tip).

    Single source of truth for where the maple's lobes radiate, shared by the mesh
    outline (:func:`_outline_palmate`), the leaf albedo + vein/normal mask
    (``geom/_textures.py``), and the per-rib hero-blade fold
    (``geom/leaf_blade3d.py``) — so geometry, texture, and 3D relief stay aligned.
    Returns ``(anchor (2,), tips (_PALMATE_LOBES, 2))``.
    """
    cx, cy, angles, radii = _palmate_fan(L, W)
    anchor = np.array([cx, cy], dtype=np.float64)
    tips = np.array([[cx + R * np.cos(a), cy + R * np.sin(a)]
                     for a, R in zip(angles, radii, strict=True)], dtype=np.float64)
    return anchor, tips


def _outline_palmate(L: float, W: float, samples_per_lobe: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """5 lobes fanning UPWARD from the petiole attachment at the base (0, 0).

    The blade origin (0, 0) is lifted onto the petiole tip (geom/leaves.py), so the
    lamina must reach it. The prior design radiated 5 lobes over a full 360° from a
    center at (0, 0.4*L), which left (0, 0) in the basal notch between the two
    downward lobes — the petiole tip dangled in empty space and the leaf read as
    detached. Here the lobes fan over an upward ~150° arc from a low center (shared
    via :func:`_palmate_fan`), the two outer lobes sweep back down to (0, 0), and
    the central lobe is longest — matching the palmate venation baked in
    geom/_textures.leaf_vein_mask.
    """
    n_lobes = _PALMATE_LOBES
    cx, cy, peak_angles, peak_radii = _palmate_fan(L, W)

    def pt(theta: float, R: float) -> np.ndarray:
        return np.array([cx + R * np.cos(theta), cy + R * np.sin(theta)])

    boundary_pts = [np.array([0.0, 0.0])]   # petiole attachment at the base
    for k in range(n_lobes):
        th, Rk = peak_angles[k], peak_radii[k]
        boundary_pts.append(pt(th, Rk))
        if k < n_lobes - 1:                  # inter-lobe sinus + walk to next peak
            th2, Rk2 = peak_angles[k + 1], peak_radii[k + 1]
            thv, Rv = 0.5 * (th + th2), 0.55 * min(peak_radii[k], Rk2)
            for s in range(1, samples_per_lobe):
                t = s / samples_per_lobe
                boundary_pts.append(pt(th + t * (thv - th), Rk + t * (Rv - Rk)))
            boundary_pts.append(pt(thv, Rv))
            for s in range(1, samples_per_lobe):
                t = s / samples_per_lobe
                boundary_pts.append(pt(thv + t * (th2 - thv), Rv + t * (Rk2 - Rv)))

    boundary = np.array(boundary_pts, dtype=np.float64)
    anchor = np.array([cx, cy], dtype=np.float64)   # radiating centre → star-convex
    # Defensive CCW check; reverse if signed area came out negative.
    x, y = boundary[:, 0], boundary[:, 1]
    area = 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
    if area < 0:
        boundary = boundary[::-1].copy()
    return boundary, anchor


def _triangulate_fan(
    boundary: np.ndarray, anchor: np.ndarray, subdivisions: int = 0
) -> tuple[np.ndarray, np.ndarray]:
    """Fan triangulate ``boundary`` from ``anchor``. ``positions[0]`` is the anchor.

    ``subdivisions == 0`` is the legacy single fan: one triangle per boundary edge,
    no interior vertices. ``subdivisions > 0`` inserts that many concentric rings
    between the anchor and the boundary (each ring is the boundary lerped toward the
    anchor) and triangulates anchor→ring₁ as a fan + ringⱼ→ringⱼ₊₁ as quad strips,
    so the lamina has interior vertices to curve across. The outlines are star-convex
    from the anchor, so every interior ring stays inside the polygon. Winding stays
    CCW in (u, v) → +z face normals, matching the flat convention.
    """
    n = boundary.shape[0]
    if subdivisions <= 0:
        positions = np.empty((n + 1, 2), dtype=np.float64)
        positions[0] = anchor
        positions[1:] = boundary
        indices = np.empty((n * 3,), dtype=np.uint32)
        for i in range(n):
            indices[3 * i + 0] = 0
            indices[3 * i + 1] = 1 + i
            indices[3 * i + 2] = 1 + ((i + 1) % n)
        return positions, indices

    rings = subdivisions + 1                 # ring `rings` IS the boundary
    positions = np.empty((1 + rings * n, 2), dtype=np.float64)
    positions[0] = anchor
    for j in range(1, rings + 1):
        t = j / rings
        positions[1 + (j - 1) * n : 1 + j * n] = anchor[None, :] + t * (boundary - anchor[None, :])

    idx: list[int] = []
    r1 = 1                                    # base index of the innermost ring
    for i in range(n):                        # anchor → ring₁ fan
        a = r1 + i
        b = r1 + (i + 1) % n
        idx += [0, a, b]
    for j in range(1, rings):                 # ringⱼ → ringⱼ₊₁ quad strips
        inner = 1 + (j - 1) * n
        outer = 1 + j * n
        for i in range(n):
            a = inner + i
            b = inner + (i + 1) % n
            c = outer + i
            d = outer + (i + 1) % n
            idx += [a, c, b, b, c, d]
    indices = np.asarray(idx, dtype=np.uint32)
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
