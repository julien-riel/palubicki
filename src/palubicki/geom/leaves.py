from __future__ import annotations

import math

import numpy as np

from palubicki.geom.mesh import Material, Primitive
from palubicki.sim.tree import BudState, Tree


def build_leaves_primitive(
    tree: Tree,
    *,
    leaf_size: float,
    material: Material,
    cluster_count: int = 1,
    aspect: float = 1.0,
    splay_deg: float = 0.0,
) -> Primitive:
    """Per surviving terminal bud, emit `cluster_count` cross-quads (8 verts each)
    azimuthally spread around the growth direction and tilted outward by splay_deg."""
    surviving = [b for b in tree.active_buds if b.state != BudState.DEAD and _is_terminal(b)]

    if not surviving:
        return Primitive(
            positions=np.zeros((0, 3), dtype=np.float32),
            normals=np.zeros((0, 3), dtype=np.float32),
            uvs=np.zeros((0, 2), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.uint32),
            material=material,
        )

    verts_per_bud = cluster_count * 8
    idx_per_bud = cluster_count * 12
    n = len(surviving)
    positions = np.empty((n * verts_per_bud, 3), dtype=np.float32)
    normals = np.empty((n * verts_per_bud, 3), dtype=np.float32)
    uvs = np.empty((n * verts_per_bud, 2), dtype=np.float32)
    indices = np.empty((n * idx_per_bud,), dtype=np.uint32)

    splay_rad = math.radians(splay_deg)

    for i, bud in enumerate(surviving):
        v_start = i * verts_per_bud
        i_start = i * idx_per_bud
        _emit_leaf_cluster(
            bud.position, bud.direction, leaf_size, cluster_count, aspect, splay_rad,
            positions[v_start : v_start + verts_per_bud],
            normals[v_start : v_start + verts_per_bud],
            uvs[v_start : v_start + verts_per_bud],
            indices[i_start : i_start + idx_per_bud],
            v_start,
        )
    return Primitive(positions=positions, normals=normals, uvs=uvs, indices=indices, material=material)


def _is_terminal(bud) -> bool:
    """A bud is 'terminal' if it sits at a node with no children internodes."""
    return len(bud.parent_node.children_internodes) == 0


def _emit_leaf_cluster(center, direction, size, cluster_count, aspect, splay_rad,
                       out_pos, out_norm, out_uv, out_idx, base):
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    right, forward = _basis_perpendicular_to(d)

    half_u = size * 0.5 * aspect
    half_v = size * 0.5
    petiole_offset = d * (size * 0.3)
    leaf_center = np.asarray(center, dtype=np.float64) + petiole_offset

    for k in range(cluster_count):
        az = 2.0 * math.pi * k / cluster_count
        rot_axis_u = math.cos(az) * right + math.sin(az) * forward
        rot_axis_w = -math.sin(az) * right + math.cos(az) * forward  # in-plane perpendicular
        leaf_up = math.cos(splay_rad) * d + math.sin(splay_rad) * rot_axis_u

        v_off = k * 8
        i_off = k * 12
        cluster_base = base + v_off
        # Quad A: (rot_axis_u, leaf_up) plane; normal = rot_axis_w
        _add_quad(leaf_center, rot_axis_u, leaf_up, half_u, half_v, rot_axis_w,
                  out_pos, out_norm, out_uv, out_idx, cluster_base, v_off, slot=0, idx_base=i_off)
        # Quad B: (rot_axis_w, leaf_up) plane; normal = rot_axis_u
        _add_quad(leaf_center, rot_axis_w, leaf_up, half_u, half_v, rot_axis_u,
                  out_pos, out_norm, out_uv, out_idx, cluster_base, v_off, slot=4, idx_base=i_off)


def _basis_perpendicular_to(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    canonical = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    right = canonical - np.dot(canonical, d) * d
    right = right / np.linalg.norm(right)
    forward = np.cross(d, right)
    return right, forward


def _add_quad(center, axis_u, axis_v, half_u, half_v, normal,
              out_pos, out_norm, out_uv, out_idx, base, v_off, slot, idx_base):
    pos_slot = v_off + slot
    out_pos[pos_slot + 0] = (center - axis_u * half_u).astype(np.float32)
    out_pos[pos_slot + 1] = (center + axis_u * half_u).astype(np.float32)
    out_pos[pos_slot + 2] = (center + axis_u * half_u + axis_v * 2 * half_v).astype(np.float32)
    out_pos[pos_slot + 3] = (center - axis_u * half_u + axis_v * 2 * half_v).astype(np.float32)
    n = np.asarray(normal, dtype=np.float32)
    for j in range(4):
        out_norm[pos_slot + j] = n
    out_uv[pos_slot + 0] = (0.0, 0.0)
    out_uv[pos_slot + 1] = (1.0, 0.0)
    out_uv[pos_slot + 2] = (1.0, 1.0)
    out_uv[pos_slot + 3] = (0.0, 1.0)
    idx_slot = idx_base + (slot // 4) * 6
    a = base + slot + 0; b = base + slot + 1
    c = base + slot + 2; d = base + slot + 3
    out_idx[idx_slot + 0] = a; out_idx[idx_slot + 1] = b; out_idx[idx_slot + 2] = c
    out_idx[idx_slot + 3] = a; out_idx[idx_slot + 4] = c; out_idx[idx_slot + 5] = d
