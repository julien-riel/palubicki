from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from palubicki.geom.mesh import Primitive

# Leaflet placement in the leaf's local (u, v) frame, in whole-leaf-size units.
#   origin_uv  : (u, v) petiole-attachment point of the leaflet
#   axis_angle : radians; leaflet v-axis = cos(a)*leaf_up + sin(a)*rot_axis_u
#   scale      : leaflet size as a multiple of the whole-leaf size
Leaflet = tuple[tuple[float, float], float, float]
# Rachis centerline segment: (start_uv, end_uv, r0, r1) in size-units; r0 is the
# radius at start_uv, r1 at end_uv (equal r0==r1 = constant-radius tube).
RachisSeg = tuple[tuple[float, float], tuple[float, float], float, float]

_OUTWARD = math.radians(60.0)   # pinnate leaflet splay from the rachis
_FAN = math.radians(55.0)       # palmate half-fan half-angle


@dataclass(frozen=True)
class CompoundLayout:
    leaflets: list[Leaflet]
    rachis_segments: list[RachisSeg]


def compound_layout(
    kind: str,
    *,
    leaflet_count: int,
    leaflet_pair_count: int,
    terminal_leaflet: bool,
    rachis_length: float,
    petiole_length: float,
    rachis_radius: float,
    petiole_taper: float = 1.0,
) -> CompoundLayout:
    if kind == "simple":
        if petiole_length > 0.0:
            r0 = rachis_radius
            r1 = rachis_radius * petiole_taper
            return CompoundLayout(
                leaflets=[((0.0, petiole_length), 0.0, 1.0)],
                rachis_segments=[((0.0, 0.0), (0.0, petiole_length), r0, r1)],
            )
        return CompoundLayout(leaflets=[((0.0, 0.0), 0.0, 1.0)], rachis_segments=[])
    if kind == "pinnate":
        return _pinnate(leaflet_count, terminal_leaflet, rachis_length,
                        petiole_length, rachis_radius)
    if kind == "palmate":
        return _palmate(leaflet_count, petiole_length, rachis_radius)
    if kind == "bipinnate":
        return _bipinnate(leaflet_pair_count, leaflet_count, rachis_length,
                          petiole_length, rachis_radius)
    raise ValueError(f"unknown compound leaf kind: {kind!r}")


def _pinnate(n_lat, terminal, rachis_length, petiole_length, radius):
    leaflets: list[Leaflet] = []
    v0, v1 = petiole_length, petiole_length + rachis_length
    n_levels = max(1, math.ceil(n_lat / 2))
    spacing = (v1 - v0) / n_levels
    lscale = min(0.6, 0.9 * spacing)
    placed = 0
    for i in range(n_levels):
        v = v0 + (i + 0.5) * spacing
        # right then left
        leaflets.append(((0.0, v), _OUTWARD, lscale))
        placed += 1
        if placed < n_lat:
            leaflets.append(((0.0, v), -_OUTWARD, lscale))
            placed += 1
    if terminal:
        leaflets.append(((0.0, v1), 0.0, lscale))
    segs: list[RachisSeg] = [
        ((0.0, 0.0), (0.0, v0), radius, radius),
        ((0.0, v0), (0.0, v1), radius, radius),
    ]
    return CompoundLayout(leaflets=leaflets, rachis_segments=segs)


def _palmate(n, petiole_length, radius):
    leaflets: list[Leaflet] = []
    lscale = 0.8
    if n == 1:
        angles = [0.0]
    else:
        angles = [(-_FAN + 2 * _FAN * k / (n - 1)) for k in range(n)]
    for a in angles:
        leaflets.append(((0.0, petiole_length), a, lscale))
    segs: list[RachisSeg] = (
        [((0.0, 0.0), (0.0, petiole_length), radius, radius)]
        if petiole_length > 0 else []
    )
    return CompoundLayout(leaflets=leaflets, rachis_segments=segs)


def _bipinnate(pair_count, leaflets_per, rachis_length, petiole_length, radius):
    leaflets: list[Leaflet] = []
    segs: list[RachisSeg] = [
        ((0.0, 0.0), (0.0, petiole_length), radius, radius),
        ((0.0, petiole_length), (0.0, petiole_length + rachis_length), radius, radius),
    ]
    v0, v1 = petiole_length, petiole_length + rachis_length
    n_levels = max(1, pair_count)
    spacing = (v1 - v0) / n_levels
    sec_len = 0.7 * spacing * leaflets_per  # secondary rachis length
    lscale = min(0.4, 0.9 * spacing)
    side_count = 0
    for i in range(n_levels):
        v = v0 + (i + 0.5) * spacing
        for sign in (+1.0, -1.0):
            if side_count >= pair_count:
                break
            sec_ang = sign * _OUTWARD
            # secondary direction unit vector in (u, v): (sin, cos) of sec_ang
            du, dv = math.sin(sec_ang), math.cos(sec_ang)
            base_u, base_v = 0.0, v
            end_u, end_v = base_u + du * sec_len, base_v + dv * sec_len
            segs.append(((base_u, base_v), (end_u, end_v), radius * 0.6, radius * 0.6))
            for j in range(leaflets_per):
                t = (j + 0.5) / leaflets_per
                ou, ov = base_u + du * sec_len * t, base_v + dv * sec_len * t
                # sub-leaflet angled outward from the secondary on alternating sides
                sub = sec_ang + (_OUTWARD if j % 2 == 0 else -_OUTWARD)
                leaflets.append(((ou, ov), sub, lscale))
            side_count += 1
    return CompoundLayout(leaflets=leaflets, rachis_segments=segs)


def resolve_leaflet_blade(geom) -> tuple[str, str, float]:
    """(shape, margin, aspect) for a leaflet: leaflet_* overrides, else inherit
    the simple-leaf values."""
    shape = geom.leaflet_shape if geom.leaflet_shape is not None else geom.leaf_shape
    margin = geom.leaflet_margin if geom.leaflet_margin is not None else geom.leaf_margin
    aspect = geom.leaflet_aspect if geom.leaflet_aspect is not None else geom.leaf_aspect
    return shape, margin, aspect


def _emit_cylinder(p0, p1, radius0, radius1, ring_sides, base_index):
    """A capped-less cylinder between 3D points p0->p1, radius0 at p0 and
    radius1 at p1 (radius0==radius1 = constant). Returns
    (positions(2R,3), normals(2R,3), uvs(2R,2), tangents(2R,4), indices(6R,)) with
    indices offset by base_index. The tangent is the ring's azimuthal direction
    (handedness +1) so the stem carries a valid TANGENT alongside the trunk."""
    # Function-local import to avoid a leaves<->compound_leaf import cycle.
    from palubicki.geom.leaves import _basis_perpendicular_to

    p0 = np.asarray(p0, dtype=np.float64)
    p1 = np.asarray(p1, dtype=np.float64)
    axis = p1 - p0
    length = float(np.linalg.norm(axis))
    if length < 1e-12:
        z = np.zeros((0, 3), np.float32)
        return (z, z, np.zeros((0, 2), np.float32),
                np.zeros((0, 4), np.float32), np.zeros((0,), np.uint32))
    axis = axis / length
    right, forward = _basis_perpendicular_to(axis)
    ang = np.linspace(0.0, 2.0 * np.pi, ring_sides, endpoint=False)
    ring = (
        np.cos(ang)[:, None] * right[None, :]
        + np.sin(ang)[:, None] * forward[None, :]
    )  # (R, 3) unit
    azi = (
        -np.sin(ang)[:, None] * right[None, :]
        + np.cos(ang)[:, None] * forward[None, :]
    )  # (R, 3) azimuthal tangent
    nrm = ring.astype(np.float32)
    bottom = p0[None, :] + radius0 * ring
    top = p1[None, :] + radius1 * ring
    positions = np.concatenate([bottom, top]).astype(np.float32)
    normals = np.concatenate([nrm, nrm])
    tangents = np.empty((2 * ring_sides, 4), np.float32)
    tangents[:, :3] = np.concatenate([azi, azi]).astype(np.float32)
    tangents[:, 3] = 1.0
    uvs = np.zeros((2 * ring_sides, 2), np.float32)
    idx: list[int] = []
    for k in range(ring_sides):
        a = k
        b = (k + 1) % ring_sides
        c = ring_sides + k
        dd = ring_sides + (k + 1) % ring_sides
        idx += [a, c, b, b, c, dd]
    indices = np.asarray(idx, dtype=np.uint32) + np.uint32(base_index)
    return positions, normals, uvs, tangents, indices


def build_rachis_primitive(
    tree, *, material, leaf_size, foliage_depth, leaf_kind, leaflet_specs,
    ring_sides=5, needle_cluster_spacing=0.0, sun_shade_k=0.0, splay_deg=0.0,
    droop_deg=0.0,
):
    """Thin stem tubes for petiole + rachis(es), lifted at every selected leaf
    site. Empty primitive for leaf_kind='simple' (no rachis)."""
    # Function-local import to avoid a leaves<->compound_leaf import cycle.
    from palubicki.geom.leaves import (
        compute_effective_leaf_size,
        leaf_basis,
        selected_leaves,
    )
    from palubicki.geom.wind import (
        LEAF_STIFFNESS,
        axis_frames,
        leaf_phase,
    )
    from palubicki.geom.wind import tier as wind_tier_of

    empty = Primitive(
        positions=np.zeros((0, 3), np.float32),
        normals=np.zeros((0, 3), np.float32),
        uvs=np.zeros((0, 2), np.float32),
        indices=np.zeros((0,), np.uint32),
        material=material,
    )
    if leaflet_specs is None:
        return empty
    layout = compound_layout(
        leaf_kind,
        leaflet_count=leaflet_specs["leaflet_count"],
        leaflet_pair_count=leaflet_specs["leaflet_pair_count"],
        terminal_leaflet=leaflet_specs["terminal_leaflet"],
        rachis_length=leaflet_specs["rachis_length"],
        petiole_length=leaflet_specs["petiole_length"],
        rachis_radius=leaflet_specs["rachis_radius"],
        petiole_taper=leaflet_specs.get("petiole_taper", 1.0),
    )
    if not layout.rachis_segments:
        return empty
    records = selected_leaves(
        tree, foliage_depth=foliage_depth,
        needle_cluster_spacing=needle_cluster_spacing,
    )
    splay_rad = math.radians(splay_deg)
    droop_rad = math.radians(droop_deg)
    origin = np.asarray(tree.root.position, dtype=np.float64)  # tree-relative phase
    frames = axis_frames(tree)  # branch-base pivot + axis tier (rides the branch swing)
    pos_chunks, nrm_chunks, uv_chunks, tan_chunks, idx_chunks = [], [], [], [], []
    wind_chunks, pivot_chunks, tier_chunks = [], [], []
    cursor = 0
    for leaf, stem_dir, source_iod, render_pos in records:
        eff = compute_effective_leaf_size(source_iod, leaf_size, sun_shade_k)
        rot_axis_u, leaf_up, _ = leaf_basis(
            stem_dir, leaf.azimuth, splay_rad, droop_rad
        )
        center = np.asarray(render_pos, dtype=np.float64)
        # Stems are tier-2 detail riding with their branch: same per-leaf phase, low
        # stiffness, pivot at the branch base (so they swing with the branch) — but
        # leafMask 0 (a stem doesn't flutter along a normal the way a blade does).
        phase = leaf_phase(render_pos, leaf.azimuth, origin)
        base, axis_order = frames.get(id(leaf.parent_node), (render_pos, 0))
        branch_pivot = np.asarray(base, dtype=np.float32)
        stem_tier = float(wind_tier_of(axis_order))

        def lift(uv, _center=center, _u=rot_axis_u, _up=leaf_up, _eff=eff):
            u, v = uv
            return _center + _eff * (u * _u + v * _up)

        for s_uv, e_uv, r0, r1 in layout.rachis_segments:
            p, nn, uv, tan, ix = _emit_cylinder(
                lift(s_uv), lift(e_uv), r0 * eff, r1 * eff, ring_sides, cursor
            )
            if p.shape[0] == 0:
                continue
            nv = p.shape[0]
            pos_chunks.append(p)
            nrm_chunks.append(nn)
            uv_chunks.append(uv)
            tan_chunks.append(tan)
            idx_chunks.append(ix)
            wind_chunks.append(np.tile(
                np.array([phase, LEAF_STIFFNESS, 0.0], np.float32), (nv, 1)))
            pivot_chunks.append(np.tile(branch_pivot, (nv, 1)))
            tier_chunks.append(np.full((nv,), stem_tier, np.float32))
            cursor += nv
    if not pos_chunks:
        return empty
    return Primitive(
        positions=np.concatenate(pos_chunks),
        normals=np.concatenate(nrm_chunks),
        uvs=np.concatenate(uv_chunks),
        indices=np.concatenate(idx_chunks),
        material=material,
        wind=np.concatenate(wind_chunks),
        pivot=np.concatenate(pivot_chunks),
        wind_tier=np.concatenate(tier_chunks),
        tangents=np.concatenate(tan_chunks),
    )
