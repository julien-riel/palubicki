from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from palubicki.geom.compound_leaf import compound_layout
from palubicki.geom.leaf_blade import build_blade
from palubicki.geom.mesh import Material, Primitive
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

    verts_per_leaf = n_planes * blade_v_count * leaflets_per_leaf
    idx_per_leaf = n_planes * blade_i_count * leaflets_per_leaf
    n = len(records)
    positions = np.empty((n * verts_per_leaf, 3), dtype=np.float32)
    normals = np.empty((n * verts_per_leaf, 3), dtype=np.float32)
    uvs = np.empty((n * verts_per_leaf, 2), dtype=np.float32)
    indices = np.empty((n * idx_per_leaf,), dtype=np.uint32)

    # Autumn tint (#61): per-vertex COLOR_0 only when a SENESCENT leaf is present
    # and a tint is configured. Otherwise colors stays None — byte-identical to
    # the pre-caducity output (all-ACTIVE / phenology-off case).
    senescing = any(leaf.state is LeafState.SENESCENT for leaf, *_ in records)
    want_colors = autumn_color is not None and senescing
    colors = np.empty((n * verts_per_leaf, 3), dtype=np.float32) if want_colors else None
    autumn = np.asarray(autumn_color, dtype=np.float32) if want_colors else None

    splay_rad = math.radians(splay_deg)
    droop_rad = math.radians(droop_deg)
    for i, (leaf, stem_dir, source_iod, render_pos) in enumerate(records):
        eff_size = compute_effective_leaf_size(source_iod, leaf_size, sun_shade_k)
        v_start = i * verts_per_leaf
        i_start = i * idx_per_leaf
        _lift_compound_leaf(
            render_pos, stem_dir, leaf.azimuth, eff_size, splay_rad, n_planes,
            leaflets, blade_pos_unit, blade_uv, blade_idx,
            positions[v_start : v_start + verts_per_leaf],
            normals[v_start : v_start + verts_per_leaf],
            uvs[v_start : v_start + verts_per_leaf],
            indices[i_start : i_start + idx_per_leaf],
            v_start, droop_rad,
        )
        if want_colors:
            # SENESCENT -> autumn tint; ACTIVE -> neutral white (COLOR_0 multiply
            # is a no-op, so green leaves render unchanged).
            colors[v_start : v_start + verts_per_leaf] = (
                autumn if leaf.state is LeafState.SENESCENT else 1.0
            )
    return Primitive(
        positions=positions, normals=normals, uvs=uvs, indices=indices,
        material=material, colors=colors,
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
    pair_area = unit_blade_area * (math.cos(splay_rad) + plane_b_factor)
    leaflet_scale_sq_sum = sum(scale * scale for (_uv, _a, scale) in layout.leaflets)
    unit_area = pair_area * leaflet_scale_sq_sum

    out: list[tuple[np.ndarray, float]] = []
    for _leaf, _stem_dir, source_iod, pos in records:
        eff = compute_effective_leaf_size(source_iod, g.leaf_size, g.leaf_sun_shade_k)
        out.append((pos, unit_area * eff * eff))
    return out


def _lift_compound_leaf(center, direction, azimuth, size, splay_rad, n_planes,
                        leaflets, blade_pos_unit, blade_uv, blade_idx,
                        out_pos, out_norm, out_uv, out_idx, base, droop_rad=0.0):
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
            )


def _lift_blade(blade_pos_unit, blade_uv, blade_idx,
                origin, basis_u, basis_v, normal, scale,
                out_pos, out_norm, out_uv, out_idx, base):
    """Lift a (u, v, 0) 2D blade into 3D along given basis vectors."""
    # blade_pos_unit[:, 0] is u, blade_pos_unit[:, 1] is v; scale to physical size.
    pu = blade_pos_unit[:, 0] * scale
    pv = blade_pos_unit[:, 1] * scale
    bu = np.asarray(basis_u, dtype=np.float64)
    bv = np.asarray(basis_v, dtype=np.float64)
    pos = origin[np.newaxis, :] + pu[:, np.newaxis] * bu[np.newaxis, :] \
          + pv[:, np.newaxis] * bv[np.newaxis, :]
    out_pos[:] = pos.astype(np.float32)
    n = np.asarray(normal, dtype=np.float32)
    out_norm[:] = n[np.newaxis, :]
    out_uv[:] = blade_uv
    out_idx[:] = blade_idx + np.uint32(base)


def _basis_perpendicular_to(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    canonical = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    right = canonical - np.dot(canonical, d) * d
    right = right / np.linalg.norm(right)
    forward = np.cross(d, right)
    return right, forward
