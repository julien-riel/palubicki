from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from palubicki.geom.compound_leaf import compound_layout
from palubicki.geom.leaf_blade import build_blade
from palubicki.geom.leaf_blade3d import build_curved_blade
from palubicki.geom.mesh import Material, Primitive
from palubicki.geom.wind import LEAF_STIFFNESS, axis_frames, leaf_phase
from palubicki.geom.wind import tier as wind_tier_of
from palubicki.sim.tree import BudState, Internode, Leaf, LeafState, Node, Tree

if TYPE_CHECKING:
    from palubicki.config import GeomConfig

_MAX_CLUSTERS_PER_INTERNODE = 8

_DOWN = np.array([0.0, -1.0, 0.0])

# States that appear in the rendered mesh. SENESCENT leaves are dead-but-attached
# (autumn foliage / marcescence); ABSCISSED leaves have detached and are gone.
_RENDERED_LEAF_STATES = (LeafState.ACTIVE, LeafState.SENESCENT)


def leaf_basis(direction, azimuth, splay_rad, droop_rad=0.0):
    """The per-leaf orthogonal-ish frame: (rot_axis_u, leaf_up, rot_axis_w).

    rot_axis_u is the lateral (blade-width) axis at phyllotactic ``azimuth``;
    rot_axis_w is the blade normal; leaf_up is the petiole / blade-length axis,
    tilted off the stem by ``splay_rad``. ``droop_rad`` > 0 rigidly rotates all
    three axes toward gravity (-Y), so the petiole and blade bend down together
    while the rot_axis_u<->leaf_up angle (the cos(splay) blade-area shear) is
    preserved. droop_rad == 0 reproduces the legacy inline math exactly.
    """
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    right, forward = _basis_perpendicular_to(d)
    rot_axis_u = math.cos(azimuth) * right + math.sin(azimuth) * forward
    rot_axis_w = -math.sin(azimuth) * right + math.cos(azimuth) * forward
    leaf_up = math.cos(splay_rad) * d + math.sin(splay_rad) * rot_axis_u
    if droop_rad != 0.0:
        k = np.cross(leaf_up, _DOWN)
        kn = float(np.linalg.norm(k))
        if kn > 1e-9:
            k = k / kn
            c, s = math.cos(droop_rad), math.sin(droop_rad)

            def _rot(v):
                return v * c + np.cross(k, v) * s + k * float(np.dot(k, v)) * (1.0 - c)

            rot_axis_u = _rot(rot_axis_u)
            leaf_up = _rot(leaf_up)
            rot_axis_w = _rot(rot_axis_w)
    return rot_axis_u, leaf_up, rot_axis_w


def compute_effective_leaf_size(
    internode: Internode | None,
    leaf_size: float,
    sun_shade_k: float,
) -> float:
    """Effective per-site leaf edge length under sun/shade scaling.

    Shared by build_leaves_primitive (renderer) and sim/diagnostics.py
    (total_leaf_area). Keeps the harness from drifting from what the .glb
    actually contains.
    """
    lf = internode.light_factor if internode is not None else 1.0
    if sun_shade_k > 0.0:
        eff = leaf_size * (1.0 + sun_shade_k * (1.0 - lf))
        return max(0.5 * leaf_size, min(2.0 * leaf_size, eff))
    return leaf_size


def fascicle_offsets(count: int, spread_deg: float) -> list[tuple[float, float]]:
    """Per-member ``(azimuth_offset, extra_splay_rad)`` for a needle fascicle (#7).

    A fascicle is the bundle of 2–5 needles a pine seats at one position. Each
    member is distributed ``2π/count`` apart in azimuth around the shared bundle
    axis and tilted off it by ``spread_deg`` (added on top of the base
    ``leaf_splay_deg``), giving the symmetric V/star a real pine bundle shows.

    ``count <= 1`` returns ``[(0.0, 0.0)]`` — the single no-op member — and the
    callers special-case ``offset == 0.0`` so the legacy single-needle lift is
    reproduced byte-for-byte (every broadleaf species, and conifers before opting
    in, stay identical). Shared by :func:`build_leaves_primitive` (geometry) and
    :func:`leaf_area_records` (occluding area) so the ``.glb`` and the light grid
    cannot disagree about fascicle multiplicity.
    """
    if count <= 1:
        return [(0.0, 0.0)]
    extra_splay = math.radians(spread_deg)
    step = 2.0 * math.pi / count
    return [(m * step, extra_splay) for m in range(count)]


def build_leaves_primitive(
    tree: Tree,
    *,
    leaf_size: float,
    material: Material,
    aspect: float = 1.0,
    splay_deg: float = 0.0,
    droop_deg: float = 0.0,
    foliage_depth: int = 1,
    needle_cluster_spacing: float = 0.0,
    sun_shade_k: float = 0.0,
    leaf_shape: str = "ovate",
    leaf_margin: str = "entire",
    leaf_margin_depth: float = 0.0,
    leaf_margin_count: int = 0,
    leaf_kind: str = "simple",
    leaflet_specs: dict | None = None,
    autumn_color: tuple[float, float, float] | None = None,
    blade_fold_deg: float = 0.0,
    blade_curl: float = 0.0,
    fascicle_count: int = 1,
    fascicle_spread_deg: float = 0.0,
) -> Primitive:
    """Triangulate every selected (apex-proximal, ACTIVE) leaf on the tree.

    Each Leaf already encodes one phyllotactically-seated cluster member (the fan
    moved to emission time, #14), so there is no render-time cluster_count fan.
    ``n_planes`` is 2 (cross-blade) for linear needles, 1 otherwise. Blade size
    scales by compute_effective_leaf_size(source_internode, ...).

    ``leaf_kind`` + ``leaflet_specs`` choose the per-leaf layout via
    :func:`palubicki.geom.compound_leaf.compound_layout`. The default
    ``leaf_kind="simple"`` (or ``leaflet_specs=None``) is a single identity
    leaflet ``((0,0), 0.0, 1.0)`` and is byte-identical to the legacy single-blade
    output. For compound kinds, ``leaflet_specs`` carries the layout knobs
    (``leaflet_count``, ``leaflet_pair_count``, ``terminal_leaflet``,
    ``rachis_length``, ``petiole_length``, ``rachis_radius``).
    """
    records = selected_leaves(
        tree, foliage_depth=foliage_depth,
        needle_cluster_spacing=needle_cluster_spacing,
    )
    if not records:
        return Primitive(
            positions=np.zeros((0, 3), dtype=np.float32),
            normals=np.zeros((0, 3), dtype=np.float32),
            uvs=np.zeros((0, 2), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.uint32),
            material=material,
        )

    if leaf_kind == "simple" or leaflet_specs is None:
        pet_len = 0.0 if leaflet_specs is None else leaflet_specs.get("petiole_length", 0.0)
        pet_taper = 1.0 if leaflet_specs is None else leaflet_specs.get("petiole_taper", 1.0)
        pet_rad = 0.0 if leaflet_specs is None else leaflet_specs.get("rachis_radius", 0.0)
        layout = compound_layout(
            "simple", leaflet_count=1, leaflet_pair_count=0,
            terminal_leaflet=False, rachis_length=1.0,
            petiole_length=pet_len, rachis_radius=pet_rad, petiole_taper=pet_taper,
        )
    else:
        layout = compound_layout(
            leaf_kind,
            leaflet_count=leaflet_specs["leaflet_count"],
            leaflet_pair_count=leaflet_specs["leaflet_pair_count"],
            terminal_leaflet=leaflet_specs["terminal_leaflet"],
            rachis_length=leaflet_specs["rachis_length"],
            petiole_length=leaflet_specs["petiole_length"],
            rachis_radius=leaflet_specs["rachis_radius"],
        )
    leaflets = layout.leaflets
    leaflets_per_leaf = len(leaflets)

    blade_pos_unit, _, blade_uv, blade_idx = build_blade(
        length=1.0, width=aspect, shape=leaf_shape, margin=leaf_margin,
        margin_depth=leaf_margin_depth, margin_count=leaf_margin_count,
    )
    blade_v_count = blade_pos_unit.shape[0]
    blade_i_count = blade_idx.shape[0]
    n_planes = 2 if leaf_shape == "linear" else 1

    # #7: fascicle members. Needle-only — broadleaves keep fasc_count == 1 (a single
    # no-op member) so their geometry stays byte-identical. Each conifer needle
    # position then emits fasc_count needles fanned around the shared bundle axis.
    fasc_count = fascicle_count if leaf_shape == "linear" else 1
    members = fascicle_offsets(fasc_count, fascicle_spread_deg)

    # Hero blade (P2, geom/leaf_blade3d.py): displace the flat outline into a folded,
    # recurved blade with smooth per-vertex normals + tangents. Opt-in (fold/curl > 0)
    # and broadleaf-only — flat needles (n_planes == 2) keep the legacy plane, and
    # zero fold/curl returns the byte-identical flat blade. The (u, v) footprint is
    # unchanged, so leaf_area_records (light grid) is unaffected either way.
    blade_norm_local: np.ndarray | None = None
    blade_tan_local: np.ndarray | None = None
    if (blade_fold_deg > 0.0 or blade_curl != 0.0) and n_planes == 1:
        blade_pos_unit, blade_norm_local, blade_tan_local = build_curved_blade(
            blade_pos_unit, blade_uv, blade_idx,
            fold_deg=blade_fold_deg, curl=blade_curl, aspect=aspect,
        )

    verts_per_leaf = n_planes * blade_v_count * leaflets_per_leaf
    idx_per_leaf = n_planes * blade_i_count * leaflets_per_leaf
    # One blade-group per (record × fascicle member): vert/index count grows
    # strictly linearly with fascicle_count.
    n_groups = len(records) * fasc_count
    positions = np.empty((n_groups * verts_per_leaf, 3), dtype=np.float32)
    normals = np.empty((n_groups * verts_per_leaf, 3), dtype=np.float32)
    uvs = np.empty((n_groups * verts_per_leaf, 2), dtype=np.float32)
    indices = np.empty((n_groups * idx_per_leaf,), dtype=np.uint32)

    # Wind contract (geom/wind.py): leafMask = 1 (flutter), near-zero stiffness
    # (always flexible), per-leaf phase so the canopy shimmers out of step. pivot +
    # wind_tier come from the leaf's branch axis (so foliage rides that branch's
    # swing and a trunk-apex leaf stays tier 0); TANGENT is the blade frame's U axis.
    wind = np.empty((n_groups * verts_per_leaf, 3), dtype=np.float32)
    pivot = np.empty((n_groups * verts_per_leaf, 3), dtype=np.float32)
    wind_tier = np.empty((n_groups * verts_per_leaf,), dtype=np.float32)
    tangents = np.empty((n_groups * verts_per_leaf, 4), dtype=np.float32)

    # Autumn tint (#61): per-vertex COLOR_1 (tint) only when a SENESCENT leaf is
    # present and a tint is configured. Otherwise tint stays None — byte-identical
    # to the pre-caducity output (all-ACTIVE / phenology-off case).
    senescing = any(leaf.state is LeafState.SENESCENT for leaf, *_ in records)
    want_colors = autumn_color is not None and senescing
    colors = np.empty((n_groups * verts_per_leaf, 3), dtype=np.float32) if want_colors else None
    autumn = np.asarray(autumn_color, dtype=np.float32) if want_colors else None

    splay_rad = math.radians(splay_deg)
    droop_rad = math.radians(droop_deg)
    origin = np.asarray(tree.root.position, dtype=np.float64)  # tree-relative phase
    # Pivot + tier = the leaf's branch axis (same as that twig's bark), so foliage
    # rides the tier-1 branch swing — NOT the leaf's own seat (which gives ~0 arm).
    frames = axis_frames(tree)
    for i, (leaf, stem_dir, source_iod, render_pos) in enumerate(records):
        eff_size = compute_effective_leaf_size(source_iod, leaf_size, sun_shade_k)
        # All members of a bundle ride the same branch -> share one phase / pivot /
        # tier (computed once per record). leafMask 1: every needle flutters.
        phase = leaf_phase(render_pos, leaf.azimuth, origin)
        branch_pivot, axis_order = frames.get(id(leaf.parent_node), (render_pos, 0))
        bp = np.asarray(branch_pivot, dtype=np.float32)
        tier = float(wind_tier_of(axis_order))
        for m, (az_off, extra_splay) in enumerate(members):
            # offset == 0.0 -> pass the original untouched. fasc_count == 1 returns
            # (0.0, 0.0) so it reproduces the legacy lift byte-for-byte; in a multi-
            # member bundle the m == 0 member keeps the legacy AZIMUTH but, like every
            # member, receives the bundle's extra_splay (the whole tuft splays).
            az = leaf.azimuth if az_off == 0.0 else leaf.azimuth + az_off
            sp = splay_rad if extra_splay == 0.0 else splay_rad + extra_splay
            v_start = (i * fasc_count + m) * verts_per_leaf
            i_start = (i * fasc_count + m) * idx_per_leaf
            _lift_compound_leaf(
                render_pos, stem_dir, az, eff_size, sp, n_planes,
                leaflets, blade_pos_unit, blade_uv, blade_idx,
                positions[v_start : v_start + verts_per_leaf],
                normals[v_start : v_start + verts_per_leaf],
                uvs[v_start : v_start + verts_per_leaf],
                indices[i_start : i_start + idx_per_leaf],
                v_start, droop_rad,
                tangents[v_start : v_start + verts_per_leaf],
                blade_norm_local, blade_tan_local,
            )
            wind[v_start : v_start + verts_per_leaf] = (phase, LEAF_STIFFNESS, 1.0)
            pivot[v_start : v_start + verts_per_leaf] = bp
            wind_tier[v_start : v_start + verts_per_leaf] = tier
            if want_colors:
                # SENESCENT -> autumn tint; ACTIVE -> neutral white (COLOR_1 multiply
                # is a no-op, so green leaves render unchanged).
                colors[v_start : v_start + verts_per_leaf] = (
                    autumn if leaf.state is LeafState.SENESCENT else 1.0
                )
    return Primitive(
        positions=positions, normals=normals, uvs=uvs, indices=indices,
        material=material, tint=colors, wind=wind, pivot=pivot,
        wind_tier=wind_tier, tangents=tangents,
    )


def _leaf_bearing_nodes(
    tree: Tree, foliage_depth: int
) -> list[tuple[Node, np.ndarray, Internode | None]]:
    """Return (node, direction, source_internode) for every leaf-bearing node:
    living terminal apices plus up to (foliage_depth-1) nodes walked back along
    each apex's parent chain (deduped). This is the retention rule shared by both
    the legacy node-clustered path and the along-shoot path.

    Direction is the apex bud's growth direction for apices, the parent-internode
    tangent for walked-back nodes (matching the historical foliage_depth>1 behavior).
    """
    out: list[tuple[Node, np.ndarray, Internode | None]] = []
    apex_nodes: list[Node] = []
    for bud in tree.active_buds:
        if bud.state == BudState.DEAD:
            continue
        node = bud.parent_node
        if len(node.children_internodes) != 0:
            continue
        out.append((node, np.asarray(bud.direction, dtype=np.float64), node.parent_internode))
        apex_nodes.append(node)

    if foliage_depth <= 1:
        return out

    visited: set[int] = {id(n) for n in apex_nodes}
    for apex in apex_nodes:
        current = apex
        for _ in range(foliage_depth - 1):
            if current.parent_internode is None:
                break
            current = current.parent_internode.parent_node
            if id(current) in visited:
                break
            visited.add(id(current))
            if current.parent_internode is not None:
                parent_node = current.parent_internode.parent_node
                cur_bent = current.position + current.sag_offset
                par_bent = parent_node.position + parent_node.sag_offset
                seg = cur_bent - par_bent
                seg_norm = float(np.linalg.norm(seg))
                direction = seg / seg_norm if seg_norm > 1e-12 else np.array([0.0, 1.0, 0.0])
            else:
                direction = np.array([0.0, 1.0, 0.0])
            out.append((current, np.asarray(direction, dtype=np.float64), current.parent_internode))
    return out


def selected_leaves(
    tree: Tree, *, foliage_depth: int, needle_cluster_spacing: float = 0.0
) -> list[tuple[Leaf, np.ndarray, Internode | None, np.ndarray]]:
    """The apex-proximal, rendered leaves actually drawn this build.

    Returns (leaf, stem_direction, source_internode, render_position) per drawn
    blade-group. Shared by the renderer and sim/diagnostics so the .glb and the
    leaf-area metric cannot drift. Rendered states are ACTIVE + SENESCENT (the
    latter dead-but-attached autumn / marcescent foliage, #61); ABSCISSED leaves
    have detached and are skipped. The foliage_depth apex filter remains the MVP
    stand-in for full caducity coverage on old wood.

    needle_cluster_spacing > 0 (conifers) fans each leaf into up to
    _MAX_CLUSTERS_PER_INTERNODE positions along the (bent) parent segment, using
    the segment tangent as the stem direction (matching the legacy along-shoot
    placement). Broadleaves render one group at the node tip.
    """
    if foliage_depth < 1:
        return []
    out: list[tuple[Leaf, np.ndarray, Internode | None, np.ndarray]] = []
    for node, direction, source_iod in _leaf_bearing_nodes(tree, foliage_depth):
        active = [lf for lf in node.leaves if lf.state in _RENDERED_LEAF_STATES]
        if not active:
            continue
        node_pos = np.asarray(node.position + node.sag_offset, dtype=np.float64)
        node_dir = np.asarray(direction, dtype=np.float64)
        if needle_cluster_spacing > 0.0 and source_iod is not None:
            par = source_iod.parent_node
            par_pos = np.asarray(par.position + par.sag_offset, dtype=np.float64)
            seg = node_pos - par_pos
            seg_len = float(np.linalg.norm(seg))
            if seg_len < 1e-12:
                positions = [(node_pos, node_dir)]
            else:
                seg_dir = seg / seg_len
                n = int(seg_len / needle_cluster_spacing) + 1
                n = max(1, min(_MAX_CLUSTERS_PER_INTERNODE, n))
                positions = [(par_pos + ((k + 1) / n) * seg, seg_dir) for k in range(n)]
        else:
            positions = [(node_pos, node_dir)]
        for leaf in active:
            for pos, stem_dir in positions:
                out.append((leaf, stem_dir, source_iod, pos))
    return out


def leaf_area_records(
    tree: Tree, g: GeomConfig
) -> list[tuple[np.ndarray, float]]:
    """(render_position, projected blade-group area) for every rendered leaf.

    Single source of truth for the area a leaf occludes — consumed by both the
    self-shading LAI deposit (``sim/light.py``) and the ``total_leaf_area``
    diagnostic (``sim/diagnostics.py``), so the light grid and the harness cannot
    drift from each other or from the rendered ``.glb``. Mirrors
    :func:`build_leaves_primitive`'s geometry: each :func:`selected_leaves`
    record contributes ``pair_area * eff² * Σ leaflet_scale²``, where ``pair_area``
    folds the ``cos(splay)`` plane-A shear and (for linear needles) the
    cross-blade plane B, and ``eff`` is the sun/shade-scaled edge length at the
    record's source internode. For ``leaf_kind="simple"`` the layout is a single
    unit-scale leaflet, so the per-record area is bit-for-bit the pre-compound
    value (the ``total_leaf_area`` species pins do not move).
    """
    from palubicki.geom.compound_leaf import resolve_leaflet_blade

    records = selected_leaves(
        tree, foliage_depth=g.foliage_depth,
        needle_cluster_spacing=g.needle_cluster_spacing,
    )
    if not records:
        return []

    if g.leaf_kind == "simple":
        layout = compound_layout(
            "simple", leaflet_count=1, leaflet_pair_count=0,
            terminal_leaflet=False, rachis_length=1.0,
            petiole_length=0.0, rachis_radius=0.0,
        )
        b_shape, b_margin, b_aspect = g.leaf_shape, g.leaf_margin, g.leaf_aspect
    else:
        layout = compound_layout(
            g.leaf_kind, leaflet_count=g.leaflet_count,
            leaflet_pair_count=g.leaflet_pair_count,
            terminal_leaflet=g.terminal_leaflet,
            rachis_length=g.rachis_length_ratio,
            petiole_length=g.petiole_length_ratio,
            rachis_radius=g.rachis_radius_ratio,
        )
        b_shape, b_margin, b_aspect = resolve_leaflet_blade(g)

    blade_pos, _, _, blade_idx = build_blade(
        length=1.0, width=b_aspect, shape=b_shape,
        margin=b_margin, margin_depth=g.leaf_margin_depth,
        margin_count=g.leaf_margin_count,
    )
    pos2d = blade_pos.astype(np.float64)
    tris = blade_idx.reshape(-1, 3)
    e1 = pos2d[tris[:, 1]] - pos2d[tris[:, 0]]
    e2 = pos2d[tris[:, 2]] - pos2d[tris[:, 0]]
    unit_blade_area = float(0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum())

    splay_rad = math.radians(g.leaf_splay_deg)
    n_planes = 2 if b_shape == "linear" else 1
    plane_b_factor = 1.0 if n_planes == 2 else 0.0
    leaflet_scale_sq_sum = sum(scale * scale for (_uv, _a, scale) in layout.leaflets)

    # #7: one area record per (position × fascicle member), mirroring
    # build_leaves_primitive exactly — each member's extra splay shears its plane-A
    # blade by cos(splay + extra). Needle-only; broadleaves get the single no-op
    # member, so the per-record area (and the total_leaf_area species pins) are
    # bit-for-bit unchanged. A 5-needle pine fascicle deposits 5× the needle area
    # into its cell, so the conifer LAI grid now reflects real fascicle multiplicity.
    fasc_count = g.fascicle_count if b_shape == "linear" else 1
    member_unit_area: list[float] = []
    for _az, extra_splay in fascicle_offsets(fasc_count, g.fascicle_spread_deg):
        sp = splay_rad if extra_splay == 0.0 else splay_rad + extra_splay
        member_unit_area.append(
            unit_blade_area * (math.cos(sp) + plane_b_factor) * leaflet_scale_sq_sum
        )

    out: list[tuple[np.ndarray, float]] = []
    for _leaf, _stem_dir, source_iod, pos in records:
        eff = compute_effective_leaf_size(source_iod, g.leaf_size, g.leaf_sun_shade_k)
        e2 = eff * eff
        for unit_area in member_unit_area:
            out.append((pos, unit_area * e2))
    return out


def _lift_compound_leaf(center, direction, azimuth, size, splay_rad, n_planes,
                        leaflets, blade_pos_unit, blade_uv, blade_idx,
                        out_pos, out_norm, out_uv, out_idx, base, droop_rad=0.0,
                        out_tan=None, blade_norm_local=None, blade_tan_local=None):
    """Lift one (possibly compound) leaf into its leaflet blades at ``center``.

    Reconstructs the leaf basis from the render-time stem ``direction`` + the
    leaf ``azimuth`` + ``splay_rad`` — identical math to the legacy per-cluster-
    member lift, so blade area (cos(splay) plane-A shear) is preserved exactly.

    Each leaflet in ``leaflets`` is a ``((u0, v0), axis_angle, scale)`` spec in
    the leaf's local blade frame (``u`` ↔ ``rot_axis_u``, ``v`` ↔ ``leaf_up``,
    plane normal ↔ ``rot_axis_w``); offsets/scales are in whole-leaf-size units.
    The simple identity leaflet ``((0,0), 0.0, 1.0)`` reproduces the legacy
    single-blade (or cross, for ``n_planes==2``) geometry byte-for-byte.
    """
    rot_axis_u, leaf_up, rot_axis_w = leaf_basis(
        direction, azimuth, splay_rad, droop_rad
    )
    blade_v_count = blade_pos_unit.shape[0]
    blade_i_count = blade_idx.shape[0]
    leaf_center = np.asarray(center, dtype=np.float64)

    per_leaflet_v = n_planes * blade_v_count
    per_leaflet_i = n_planes * blade_i_count
    for k, ((u0, v0), axis_angle, scale) in enumerate(leaflets):
        if axis_angle == 0.0:
            lflt_u = rot_axis_u
            lflt_v = leaf_up
        else:
            c = math.cos(axis_angle)
            s = math.sin(axis_angle)
            # Rotate (rot_axis_u, leaf_up) by axis_angle about rot_axis_w
            # (rotation from +v toward +u).
            lflt_v = c * leaf_up + s * rot_axis_u
            lflt_u = c * rot_axis_u - s * leaf_up
        origin = leaf_center + size * (u0 * rot_axis_u + v0 * leaf_up)
        s_size = size * scale
        vk = k * per_leaflet_v
        ik = k * per_leaflet_i
        _lift_blade(
            blade_pos_unit, blade_uv, blade_idx,
            origin, lflt_u, lflt_v, rot_axis_w, s_size,
            out_pos[vk : vk + blade_v_count],
            out_norm[vk : vk + blade_v_count],
            out_uv[vk : vk + blade_v_count],
            out_idx[ik : ik + blade_i_count],
            base + vk,
            None if out_tan is None else out_tan[vk : vk + blade_v_count],
            blade_norm_local, blade_tan_local,
        )
        if n_planes == 2:
            vb = vk + blade_v_count
            ib = ik + blade_i_count
            _lift_blade(
                blade_pos_unit, blade_uv, blade_idx,
                origin, rot_axis_w, lflt_v, lflt_u, s_size,
                out_pos[vb : vb + blade_v_count],
                out_norm[vb : vb + blade_v_count],
                out_uv[vb : vb + blade_v_count],
                out_idx[ib : ib + blade_i_count],
                base + vb,
                None if out_tan is None else out_tan[vb : vb + blade_v_count],
            )


def _lift_blade(blade_pos_unit, blade_uv, blade_idx,
                origin, basis_u, basis_v, normal, scale,
                out_pos, out_norm, out_uv, out_idx, base, out_tan=None,
                blade_norm_local=None, blade_tan_local=None):
    """Lift a 2D (or curved 3D) blade into the leaf's world frame along the basis.

    The blade frame maps ``u → basis_u``, ``v → basis_v``, ``z → normal`` (the
    out-of-plane / adaxial axis). A flat blade has ``z ≡ 0``, so the ``z`` term is
    a no-op and, with ``blade_norm_local`` / ``blade_tan_local`` both ``None``,
    this is byte-identical to the legacy flat lift. When the hero blade
    (``geom/leaf_blade3d.py``) supplies per-vertex local normals/tangents, they
    are rotated into world space here (handedness recomputed in world space so a
    left-handed leaf basis can't invert the tangent)."""
    # blade_pos_unit[:, 0] is u, [:, 1] is v, [:, 2] is z (0 for the flat blade).
    pu = blade_pos_unit[:, 0] * scale
    pv = blade_pos_unit[:, 1] * scale
    pz = blade_pos_unit[:, 2] * scale
    bu = np.asarray(basis_u, dtype=np.float64)
    bv = np.asarray(basis_v, dtype=np.float64)
    bw = np.asarray(normal, dtype=np.float64)
    pos = origin[np.newaxis, :] + pu[:, np.newaxis] * bu[np.newaxis, :] \
          + pv[:, np.newaxis] * bv[np.newaxis, :] \
          + pz[:, np.newaxis] * bw[np.newaxis, :]
    out_pos[:] = pos.astype(np.float32)
    out_uv[:] = blade_uv
    out_idx[:] = blade_idx + np.uint32(base)

    def _lift(local):  # (Nv, 3) blade-frame vectors → world
        return (local[:, 0:1] * bu[np.newaxis, :]
                + local[:, 1:2] * bv[np.newaxis, :]
                + local[:, 2:3] * bw[np.newaxis, :])

    if blade_norm_local is None:
        out_norm[:] = np.asarray(normal, dtype=np.float32)[np.newaxis, :]
    else:
        wn = _lift(np.asarray(blade_norm_local, dtype=np.float64))
        out_norm[:] = (wn / np.linalg.norm(wn, axis=1, keepdims=True)).astype(np.float32)

    if out_tan is not None and blade_tan_local is None:
        # Flat blade: TANGENT follows +U (basis_u); MikkTSpace handedness
        # w = sign(cross(normal, T) · B) so the +V (basis_v) bitangent reconstructs.
        nf = bw
        cross_nb = np.array([
            nf[1] * bu[2] - nf[2] * bu[1],
            nf[2] * bu[0] - nf[0] * bu[2],
            nf[0] * bu[1] - nf[1] * bu[0],
        ])
        w = 1.0 if float(np.dot(cross_nb, bv)) >= 0.0 else -1.0
        out_tan[:, :3] = bu.astype(np.float32)[np.newaxis, :]
        out_tan[:, 3] = w
    elif out_tan is not None:
        # Curved blade: lift the local tangent + its (handedness-signed) bitangent.
        tl = np.asarray(blade_tan_local, dtype=np.float64)
        nl = np.asarray(blade_norm_local, dtype=np.float64)
        b_local = tl[:, 3:4] * np.cross(nl, tl[:, :3])
        world_t = _lift(tl[:, :3])
        world_n = _lift(nl)
        world_b = _lift(b_local)
        n_hat = world_n / np.linalg.norm(world_n, axis=1, keepdims=True)
        # The leaf basis (bu, bv, bw) is a SHEAR under splay (bu·bv = sin(splay) ≠ 0),
        # so a locally-orthonormal frame loses orthogonality once lifted. Gram-Schmidt
        # the world tangent against the world normal so the exported TBN stays square
        # (MikkTSpace expects T ⟂ N; a skewed basis warps normal-mapped shading).
        world_t = world_t - n_hat * np.sum(world_t * n_hat, axis=1, keepdims=True)
        wt = world_t / np.linalg.norm(world_t, axis=1, keepdims=True)
        # Handedness from the orthogonalised world frame and the lifted bitangent.
        handed = np.sign(np.sum(np.cross(n_hat, wt) * world_b, axis=1))
        handed[handed == 0.0] = 1.0
        out_tan[:, :3] = wt.astype(np.float32)
        out_tan[:, 3] = handed.astype(np.float32)


def _basis_perpendicular_to(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    canonical = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    right = canonical - np.dot(canonical, d) * d
    right = right / np.linalg.norm(right)
    forward = np.cross(d, right)
    return right, forward
