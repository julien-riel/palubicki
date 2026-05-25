from __future__ import annotations

import numpy as np

from palubicki.geom.mesh import Material, Primitive
from palubicki.sim.tree import BudState, Tree


def build_leaves_primitive(tree: Tree, *, leaf_size: float, material: Material) -> Primitive:
    """Cross-quad per surviving terminal bud."""
    surviving = [b for b in tree.active_buds if b.state != BudState.DEAD and _is_terminal(b)]

    if not surviving:
        return Primitive(
            positions=np.zeros((0, 3), dtype=np.float32),
            normals=np.zeros((0, 3), dtype=np.float32),
            uvs=np.zeros((0, 2), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.uint32),
            material=material,
        )

    n = len(surviving)
    positions = np.empty((n * 8, 3), dtype=np.float32)
    normals = np.empty((n * 8, 3), dtype=np.float32)
    uvs = np.empty((n * 8, 2), dtype=np.float32)
    indices = np.empty((n * 12,), dtype=np.uint32)

    for i, bud in enumerate(surviving):
        v_start = i * 8
        i_start = i * 12
        _emit_cross_quad(
            bud.position, bud.direction, leaf_size,
            positions[v_start : v_start + 8],
            normals[v_start : v_start + 8],
            uvs[v_start : v_start + 8],
            indices[i_start : i_start + 12],
            v_start,
        )
    return Primitive(positions=positions, normals=normals, uvs=uvs, indices=indices, material=material)


def _is_terminal(bud) -> bool:
    """A bud is 'terminal' if it sits at a node with no children internodes."""
    return len(bud.parent_node.children_internodes) == 0


def _emit_cross_quad(center, direction, size, out_pos, out_norm, out_uv, out_idx, base):
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    canonical = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    right = canonical - np.dot(canonical, d) * d
    right = right / np.linalg.norm(right)
    forward = np.cross(d, right)

    half = size * 0.5
    petiole_offset = d * (size * 0.3)
    leaf_center = np.asarray(center, dtype=np.float64) + petiole_offset
    leaf_up = d  # leaf extends along growth direction

    # Quad 1: in (right, leaf_up) plane
    _add_quad(leaf_center, right, leaf_up, half, forward, out_pos, out_norm, out_uv, out_idx, base, slot=0)
    # Quad 2: in (forward, leaf_up) plane
    _add_quad(leaf_center, forward, leaf_up, half, right, out_pos, out_norm, out_uv, out_idx, base, slot=4)


def _add_quad(center, axis_u, axis_v, half, normal, out_pos, out_norm, out_uv, out_idx, base, slot):
    out_pos[slot + 0] = (center - axis_u * half).astype(np.float32)
    out_pos[slot + 1] = (center + axis_u * half).astype(np.float32)
    out_pos[slot + 2] = (center + axis_u * half + axis_v * 2 * half).astype(np.float32)
    out_pos[slot + 3] = (center - axis_u * half + axis_v * 2 * half).astype(np.float32)
    n = np.asarray(normal, dtype=np.float32)
    for j in range(4):
        out_norm[slot + j] = n
    out_uv[slot + 0] = (0.0, 0.0)
    out_uv[slot + 1] = (1.0, 0.0)
    out_uv[slot + 2] = (1.0, 1.0)
    out_uv[slot + 3] = (0.0, 1.0)
    idx_slot = (slot // 4) * 6
    a = base + slot + 0; b = base + slot + 1
    c = base + slot + 2; d = base + slot + 3
    out_idx[idx_slot + 0] = a; out_idx[idx_slot + 1] = b; out_idx[idx_slot + 2] = c
    out_idx[idx_slot + 3] = a; out_idx[idx_slot + 4] = c; out_idx[idx_slot + 5] = d
