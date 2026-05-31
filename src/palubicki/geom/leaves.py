from __future__ import annotations

import math

import numpy as np

from palubicki.geom.leaf_blade import build_blade
from palubicki.geom.mesh import Material, Primitive
from palubicki.sim.tree import BudState, Internode, Leaf, LeafState, Node, Tree

_MAX_CLUSTERS_PER_INTERNODE = 8


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
    foliage_depth: int = 1,
    needle_cluster_spacing: float = 0.0,
    sun_shade_k: float = 0.0,
    leaf_shape: str = "ovate",
    leaf_margin: str = "entire",
    leaf_margin_depth: float = 0.0,
    leaf_margin_count: int = 0,
) -> Primitive:
    """Triangulate every selected (apex-proximal, ACTIVE) leaf on the tree.

    Each Leaf already encodes one phyllotactically-seated cluster member (the fan
    moved to emission time, #14), so there is no render-time cluster_count fan.
    ``n_planes`` is 2 (cross-blade) for linear needles, 1 otherwise. Blade size
    scales by compute_effective_leaf_size(source_internode, ...).
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

    blade_pos_unit, _, blade_uv, blade_idx = build_blade(
        length=1.0, width=aspect, shape=leaf_shape, margin=leaf_margin,
        margin_depth=leaf_margin_depth, margin_count=leaf_margin_count,
    )
    blade_v_count = blade_pos_unit.shape[0]
    blade_i_count = blade_idx.shape[0]
    n_planes = 2 if leaf_shape == "linear" else 1

    verts_per_leaf = n_planes * blade_v_count
    idx_per_leaf = n_planes * blade_i_count
    n = len(records)
    positions = np.empty((n * verts_per_leaf, 3), dtype=np.float32)
    normals = np.empty((n * verts_per_leaf, 3), dtype=np.float32)
    uvs = np.empty((n * verts_per_leaf, 2), dtype=np.float32)
    indices = np.empty((n * idx_per_leaf,), dtype=np.uint32)

    splay_rad = math.radians(splay_deg)
    for i, (leaf, stem_dir, source_iod, render_pos) in enumerate(records):
        eff_size = compute_effective_leaf_size(source_iod, leaf_size, sun_shade_k)
        v_start = i * verts_per_leaf
        i_start = i * idx_per_leaf
        _lift_leaf(
            render_pos, stem_dir, leaf.azimuth, eff_size, splay_rad, n_planes,
            blade_pos_unit, blade_uv, blade_idx,
            positions[v_start : v_start + verts_per_leaf],
            normals[v_start : v_start + verts_per_leaf],
            uvs[v_start : v_start + verts_per_leaf],
            indices[i_start : i_start + idx_per_leaf],
            v_start,
        )
    return Primitive(positions=positions, normals=normals, uvs=uvs, indices=indices, material=material)


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
    """The apex-proximal, ACTIVE leaves actually rendered this build.

    Returns (leaf, stem_direction, source_internode, render_position) per drawn
    blade-group. Shared by the renderer and sim/diagnostics so the .glb and the
    leaf-area metric cannot drift. The foliage_depth apex filter is the MVP
    stand-in for caducity; when caducity lands it is dropped and the ACTIVE
    state filter does the work alone.

    needle_cluster_spacing > 0 (conifers) fans each leaf into up to
    _MAX_CLUSTERS_PER_INTERNODE positions along the (bent) parent segment, using
    the segment tangent as the stem direction (matching the legacy along-shoot
    placement). Broadleaves render one group at the node tip.
    """
    if foliage_depth < 1:
        return []
    out: list[tuple[Leaf, np.ndarray, Internode | None, np.ndarray]] = []
    for node, direction, source_iod in _leaf_bearing_nodes(tree, foliage_depth):
        active = [lf for lf in node.leaves if lf.state is LeafState.ACTIVE]
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


def _lift_leaf(center, direction, azimuth, size, splay_rad, n_planes,
               blade_pos_unit, blade_uv, blade_idx,
               out_pos, out_norm, out_uv, out_idx, base):
    """Lift one phyllotactically-seated leaf (n_planes blades) at ``center``.

    Reconstructs the blade basis from the render-time stem ``direction`` + the
    leaf ``azimuth`` + ``splay_rad`` — identical math to the legacy per-cluster-
    member lift, so blade area (cos(splay) plane-A shear) is preserved exactly;
    only the azimuth now carries the phyllotactic seating.
    """
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    right, forward = _basis_perpendicular_to(d)

    blade_v_count = blade_pos_unit.shape[0]
    blade_i_count = blade_idx.shape[0]
    leaf_center = np.asarray(center, dtype=np.float64)

    rot_axis_u = math.cos(azimuth) * right + math.sin(azimuth) * forward
    rot_axis_w = -math.sin(azimuth) * right + math.cos(azimuth) * forward
    leaf_up = math.cos(splay_rad) * d + math.sin(splay_rad) * rot_axis_u

    _lift_blade(
        blade_pos_unit, blade_uv, blade_idx,
        leaf_center, rot_axis_u, leaf_up, rot_axis_w, size,
        out_pos[0:blade_v_count], out_norm[0:blade_v_count],
        out_uv[0:blade_v_count], out_idx[0:blade_i_count], base,
    )
    if n_planes == 2:
        slot_b = blade_v_count
        idx_b = blade_i_count
        _lift_blade(
            blade_pos_unit, blade_uv, blade_idx,
            leaf_center, rot_axis_w, leaf_up, rot_axis_u, size,
            out_pos[slot_b : slot_b + blade_v_count],
            out_norm[slot_b : slot_b + blade_v_count],
            out_uv[slot_b : slot_b + blade_v_count],
            out_idx[idx_b : idx_b + blade_i_count],
            base + slot_b,
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
