"""Curved/folded 3D hero leaf blade (export pipeline P2, design §6.3, D10).

Lofts the flat 2D outline that :func:`palubicki.geom.leaf_blade.build_blade`
triangulates (the ``(u, v, 0)`` plane) into a **hero** blade with a midrib crease
and a longitudinal recurve, then recomputes a smooth per-vertex normal + a
MikkTSpace tangent frame from the displaced surface. A real curved blade reads
the back-light, self-shadows, has a correct silhouette, and — being mostly
opaque — kills the alpha-test/overdraw cost a flat alpha card pays (design D10);
the flat alpha-MASK card stays the mid/far-LOD and grass representation (P4).

The two deformations, in the unit-blade param (length 1, width = ``aspect``,
``u`` lateral, ``v`` base→tip):

- **midrib keel** — a shallow V across ``u``: the lamina lifts ``tan(fold)·|u|``
  out of plane on each side of the midrib (``u=0``), tapered to flat at the
  petiole and the tip so the crease lives in the blade body.
- **longitudinal recurve** — the tip arcs ``curl·v²`` *below* the plane, the
  gentle droop of a held leaf.

Geometry-only and **opt-in**: with ``fold_deg == 0`` and ``curl == 0`` the blade
is the original flat plane (``z ≡ 0``, normal ``+z``, tangent ``+u``) and callers
take the legacy byte-identical path — the projected ``(u, v)`` footprint never
changes, so the leaf-area metric (``sim/light.py`` / diagnostics) is untouched
whether or not the hero blade is enabled.
"""
from __future__ import annotations

import math

import numpy as np

_EPS = 1e-9


def displace_blade(
    positions2d: np.ndarray,
    *,
    fold_deg: float,
    curl: float,
    aspect: float,
    cup: float = 0.0,
    lobe_axes: tuple[np.ndarray, np.ndarray] | None = None,
) -> np.ndarray:
    """Return the blade's per-vertex out-of-plane ``z`` (``(N,)`` float64).

    ``positions2d`` is the flat ``(N, 3)`` blade (``z`` ignored). All knobs 0/None
    → all-zero displacement (the legacy flat plane).

    - ``fold_deg`` — midrib crease half-angle (degrees). Without ``lobe_axes`` this
      is a single central keel at ``u=0`` (``tan(fold)·|u|``); with ``lobe_axes``
      (palmate) it folds along EACH lobe rib — every vertex lifts by its
      perpendicular distance to the nearest anchor→tip ray, so all five lobes
      crease along their own veins instead of one straight central line.
    - ``cup`` — concave bowl: the lamina edges curl up toward the adaxial (+z) side,
      quadratic across the half-width.
    - ``curl`` — longitudinal recurve: the tip arcs ``curl·v²`` below the plane.

    The fold/cup terms are eased to flat at the petiole (``v→0``) and tip (``v→1``)
    by a ``sqrt(sin(πv))`` arch so the relief lives in the blade body and the ends
    stay plane (no pinched normals there).
    """
    u = positions2d[:, 0].astype(np.float64)
    v = positions2d[:, 1].astype(np.float64)
    z = np.zeros_like(u)
    taper = np.sqrt(np.clip(np.sin(np.pi * np.clip(v, 0.0, 1.0)), 0.0, 1.0))
    if fold_deg > 0.0:
        slope = math.tan(math.radians(fold_deg))
        if lobe_axes is not None:
            z += slope * _rib_distance(u, v, lobe_axes) * taper
        else:
            z += slope * np.abs(u) * taper
    if cup > 0.0:
        # Edges rise relative to the centre line, eased to flat at both ends.
        half_w = max(1e-6, 0.5 * aspect)
        z += cup * (u / half_w) ** 2 * taper
    if curl != 0.0:
        # Recurve: tip (v=1) dips by ``curl`` below the plane, base unmoved.
        z -= curl * v * v
    return z


def _rib_distance(
    u: np.ndarray, v: np.ndarray, lobe_axes: tuple[np.ndarray, np.ndarray]
) -> np.ndarray:
    """Per-vertex perpendicular distance to the NEAREST palmate lobe rib.

    Each rib is the ray from the fan ``anchor`` toward a lobe ``tip``; the distance
    is ``|(p - anchor) × rib_dir|`` (2D cross magnitude), minimised over the ribs.
    Vertices on a rib get 0 (the crease line); the lamina between ribs lifts most.
    """
    anchor, tips = lobe_axes
    au, av = float(anchor[0]), float(anchor[1])
    pu = u - au
    pv = v - av
    out = np.full_like(u, np.inf)
    for tip in tips:
        tu, tv = float(tip[0]) - au, float(tip[1]) - av
        tn = math.hypot(tu, tv)
        if tn < 1e-9:
            continue
        tu, tv = tu / tn, tv / tn
        perp = np.abs(pu * tv - pv * tu)
        out = np.minimum(out, perp)
    out[~np.isfinite(out)] = 0.0
    return out


def tangent_frame(
    positions: np.ndarray, uvs: np.ndarray, indices: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Smooth per-vertex normals + MikkTSpace ``VEC4`` tangents for a triangulated
    surface, via area-weighted face accumulation + Lengyel's UV tangent solve.

    Returns ``(normals (N,3) f64, tangents (N,4) f64)`` with ``tangent.w`` the
    handedness ``sign(dot(cross(N, T), B))``. For the flat blade (CCW ``(u,v)``
    winding) this yields ``N=+z``, ``T=+u``, ``w=+1`` — matching the legacy flat
    convention exactly.
    """
    n = positions.shape[0]
    tris = indices.reshape(-1, 3).astype(np.intp)
    p = positions.astype(np.float64)
    w = uvs.astype(np.float64)

    e1 = p[tris[:, 1]] - p[tris[:, 0]]
    e2 = p[tris[:, 2]] - p[tris[:, 0]]
    # Face normals (un-normalised → area-weighted accumulation).
    fn = np.cross(e1, e2)

    duv1 = w[tris[:, 1]] - w[tris[:, 0]]
    duv2 = w[tris[:, 2]] - w[tris[:, 0]]
    det = duv1[:, 0] * duv2[:, 1] - duv2[:, 0] * duv1[:, 1]
    r = np.where(np.abs(det) > _EPS, 1.0 / np.where(det == 0.0, 1.0, det), 0.0)
    # Per-face tangent (∂P/∂u) and bitangent (∂P/∂v) in object space (Lengyel).
    ft = (e1 * duv2[:, 1, None] - e2 * duv1[:, 1, None]) * r[:, None]
    fb = (e2 * duv1[:, 0, None] - e1 * duv2[:, 0, None]) * r[:, None]

    norm_acc = np.zeros((n, 3))
    tan_acc = np.zeros((n, 3))
    bit_acc = np.zeros((n, 3))
    for c in range(3):
        np.add.at(norm_acc, tris[:, c], fn)
        np.add.at(tan_acc, tris[:, c], ft)
        np.add.at(bit_acc, tris[:, c], fb)

    normals = _normalize_rows(norm_acc, fallback=(0.0, 0.0, 1.0))
    # Gram-Schmidt: orthogonalise the tangent against the smoothed normal.
    proj = np.sum(normals * tan_acc, axis=1, keepdims=True)
    tan_ortho = _normalize_rows(tan_acc - normals * proj, fallback=(1.0, 0.0, 0.0))
    handed = np.sign(np.sum(np.cross(normals, tan_ortho) * bit_acc, axis=1))
    handed[handed == 0.0] = 1.0

    tangents = np.empty((n, 4), dtype=np.float64)
    tangents[:, :3] = tan_ortho
    tangents[:, 3] = handed
    return normals, tangents


def build_curved_blade(
    positions2d: np.ndarray,
    uvs: np.ndarray,
    indices: np.ndarray,
    *,
    fold_deg: float,
    curl: float,
    aspect: float,
    cup: float = 0.0,
    lobe_axes: tuple[np.ndarray, np.ndarray] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Unit hero blade: displaced ``(N,3)`` positions + smooth normals + ``VEC4``
    tangents, all in the blade's local ``(u, v, z)`` frame (``+z`` = adaxial face
    normal). Lifted per-leaf by ``geom/leaves.py``."""
    z = displace_blade(
        positions2d, fold_deg=fold_deg, curl=curl, aspect=aspect,
        cup=cup, lobe_axes=lobe_axes,
    )
    pos3d = positions2d.astype(np.float64, copy=True)
    pos3d[:, 2] = z
    normals, tangents = tangent_frame(pos3d, uvs, indices)
    return pos3d.astype(np.float32), normals.astype(np.float32), tangents.astype(np.float32)


def _normalize_rows(a: np.ndarray, *, fallback: tuple[float, float, float]) -> np.ndarray:
    norms = np.linalg.norm(a, axis=1)
    safe = norms > _EPS
    out = np.empty_like(a)
    out[safe] = a[safe] / norms[safe, None]
    out[~safe] = np.asarray(fallback, dtype=a.dtype)
    return out
