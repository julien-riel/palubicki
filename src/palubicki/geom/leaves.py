from __future__ import annotations

import math

import numpy as np

from palubicki.geom.leaf_blade import build_blade
from palubicki.geom.mesh import Material, Primitive
from palubicki.sim.tree import BudState, Internode, Node, Tree

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
    cluster_count: int = 1,
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
    """Emit ``cluster_count`` x ``n_planes`` triangulated blades per foliage site.

    ``n_planes`` is 2 (cross-blade) when ``leaf_shape == "linear"`` and 1
    otherwise. Cross-blade is only needed for shapes whose silhouette collapses
    when viewed edge-on (linear needles / rectangles). Parametric shapes
    (ovate, palmate, etc.) use a single plane per cluster member to avoid the
    perpendicular-plane sliver artifact.

    A foliage site is any node within ``foliage_depth`` internode-steps of the
    nearest terminal apex. With foliage_depth=1 this collapses back to
    "apex only" (legacy behavior).

    When ``sun_shade_k > 0`` and the source internode is known, blade size
    scales as
        eff_size = leaf_size * (1 + sun_shade_k * (1 - internode.light_factor))
    clamped to [0.5*leaf_size, 2.0*leaf_size]. Sites with no source internode
    (root apex) use light_factor=1.0 → eff_size=leaf_size.
    """
    sites = _collect_foliage_sites(tree, foliage_depth, needle_cluster_spacing)

    if not sites:
        return Primitive(
            positions=np.zeros((0, 3), dtype=np.float32),
            normals=np.zeros((0, 3), dtype=np.float32),
            uvs=np.zeros((0, 2), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.uint32),
            material=material,
        )

    # Build blade template once (unit length, width = aspect). Per-site scaling
    # is applied at lift time via eff_size.
    blade_pos_unit, _, blade_uv, blade_idx = build_blade(
        length=1.0, width=aspect, shape=leaf_shape, margin=leaf_margin,
        margin_depth=leaf_margin_depth, margin_count=leaf_margin_count,
    )
    blade_v_count = blade_pos_unit.shape[0]
    blade_i_count = blade_idx.shape[0]

    # Cross-blade (two perpendicular planes per cluster member) only makes
    # sense for shapes whose silhouette disappears when viewed edge-on
    # (linear needles / rectangles). For parametric shapes with rich
    # boundaries the perpendicular plane shows as a confusing sliver — see
    # issue #4 follow-up.
    n_planes = 2 if leaf_shape == "linear" else 1

    verts_per_site = cluster_count * n_planes * blade_v_count
    idx_per_site = cluster_count * n_planes * blade_i_count
    n = len(sites)
    positions = np.empty((n * verts_per_site, 3), dtype=np.float32)
    normals = np.empty((n * verts_per_site, 3), dtype=np.float32)
    uvs = np.empty((n * verts_per_site, 2), dtype=np.float32)
    indices = np.empty((n * idx_per_site,), dtype=np.uint32)

    splay_rad = math.radians(splay_deg)

    for i, (center, direction, source_iod) in enumerate(sites):
        eff_size = compute_effective_leaf_size(source_iod, leaf_size, sun_shade_k)
        v_start = i * verts_per_site
        i_start = i * idx_per_site
        _emit_leaf_cluster(
            center, direction, eff_size, cluster_count, splay_rad, n_planes,
            blade_pos_unit, blade_uv, blade_idx,
            positions[v_start : v_start + verts_per_site],
            normals[v_start : v_start + verts_per_site],
            uvs[v_start : v_start + verts_per_site],
            indices[i_start : i_start + idx_per_site],
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


def _collect_foliage_sites(
    tree: Tree, foliage_depth: int, needle_cluster_spacing: float = 0.0
) -> list[tuple[np.ndarray, np.ndarray, Internode | None]]:
    """Return (position, direction, source_internode) for each foliage cluster.

    needle_cluster_spacing == 0 -> one cluster at each leaf-bearing node (legacy).
    needle_cluster_spacing > 0  -> clothe each leaf-bearing internode with clusters
    spaced that many meters apart along the (bent) segment, capped at
    _MAX_CLUSTERS_PER_INTERNODE; the node end is always included.
    """
    if foliage_depth < 1:
        return []
    nodes = _leaf_bearing_nodes(tree, foliage_depth)
    sites: list[tuple[np.ndarray, np.ndarray, Internode | None]] = []
    for node, direction, source_iod in nodes:
        node_pos = np.asarray(node.position + node.sag_offset, dtype=np.float64)
        if needle_cluster_spacing <= 0.0 or source_iod is None:
            sites.append((node_pos, direction, source_iod))
            continue
        parent_node = source_iod.parent_node
        par_pos = np.asarray(parent_node.position + parent_node.sag_offset, dtype=np.float64)
        seg = node_pos - par_pos
        seg_len = float(np.linalg.norm(seg))
        if seg_len < 1e-12:
            sites.append((node_pos, direction, source_iod))
            continue
        # Clusters clothing the shoot follow the segment they sit on, so this
        # path deliberately uses the segment tangent rather than the node's
        # incoming ``direction`` (which can differ on an apex internode).
        seg_dir = seg / seg_len
        n = int(seg_len / needle_cluster_spacing) + 1
        n = max(1, min(_MAX_CLUSTERS_PER_INTERNODE, n))
        for k in range(n):
            f = (k + 1) / n
            sites.append((par_pos + f * seg, seg_dir, source_iod))
    return sites


def _emit_leaf_cluster(center, direction, size, cluster_count, splay_rad, n_planes,
                       blade_pos_unit, blade_uv, blade_idx,
                       out_pos, out_norm, out_uv, out_idx, base):
    """Emit ``cluster_count * n_planes`` triangulated blades per foliage site.

    ``n_planes``: 1 = single plane per cluster member (parametric shapes —
    avoids the cross-blade sliver artifact); 2 = cross-blade (linear shapes,
    where a single plane viewed edge-on is invisible).
    """
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    right, forward = _basis_perpendicular_to(d)

    blade_v_count = blade_pos_unit.shape[0]
    blade_i_count = blade_idx.shape[0]
    leaf_center = np.asarray(center, dtype=np.float64)

    for k in range(cluster_count):
        az = 2.0 * math.pi * k / cluster_count
        rot_axis_u = math.cos(az) * right + math.sin(az) * forward
        rot_axis_w = -math.sin(az) * right + math.cos(az) * forward
        leaf_up = math.cos(splay_rad) * d + math.sin(splay_rad) * rot_axis_u

        # Plane A: basis_u = rot_axis_u, basis_v = leaf_up, normal = rot_axis_w
        slot_a = k * n_planes * blade_v_count
        idx_a = k * n_planes * blade_i_count
        _lift_blade(
            blade_pos_unit, blade_uv, blade_idx,
            leaf_center, rot_axis_u, leaf_up, rot_axis_w, size,
            out_pos[slot_a : slot_a + blade_v_count],
            out_norm[slot_a : slot_a + blade_v_count],
            out_uv[slot_a : slot_a + blade_v_count],
            out_idx[idx_a : idx_a + blade_i_count],
            base + slot_a,
        )
        if n_planes == 2:
            # Plane B: basis_u = rot_axis_w, basis_v = leaf_up, normal = rot_axis_u
            slot_b = slot_a + blade_v_count
            idx_b = idx_a + blade_i_count
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
