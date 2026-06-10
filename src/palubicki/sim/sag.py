# src/palubicki/sim/sag.py
"""Mechanical sag: bend internodes toward gravity under accumulated wood load.

Post-process pass run AFTER simulate() and AFTER compute_radii(). The tree
topology stays untouched; only node positions move.

For each internode (parent → child) walked in pre-order:
  1. Compute the bending angle:
        bend = clamp(k * load * sin(θ) / max(diameter², eps), 0, max_bend)
     where ``load`` is the wood volume of the internode itself plus everything
     in the child's subtree (the mass hanging off the proximal joint), and
     ``sin(θ) = |direction × gravity_dir|`` is the perpendicular component of
     gravity relative to the internode (a horizontal branch sees the full
     moment; a vertical branch sees none). Mass per unit length is absorbed
     into the gain ``k``.
  2. Choose the rotation axis: ``(direction × gravity_dir).normalize``. This
     is the horizontal axis lying in the (direction, gravity) plane, around
     which a positive rotation bends the internode toward gravity.
  3. Build the Rodrigues rotation matrix R for ``bend`` around that axis.
  4. Apply R to every descendant of the parent (the entire subtree past this
     joint), rotating around the parent's position.

Because we walk pre-order, each child's parent has already been moved by all
ancestor bends; bends compose naturally along chains. The trunk's first
``rigid_axis_order`` levels stay rigid (real trunks don't sag noticeably).
"""
from __future__ import annotations

import math

import numpy as np

from palubicki.config import SagConfig
from palubicki.sim._vec3 import cross3, norm3
from palubicki.sim.tree import Node, Tree


def apply_sag(tree: Tree, cfg: SagConfig) -> None:
    """Idempotent: recompute sag_offset for every Node from scratch.

    Walks the tree pre-order; for each internode computes a bend angle from
    load (length × diameter² × density proxy) and applies the resulting
    rotation to all descendants' *bent* positions (position + sag_offset).
    The result is written back into each descendant's sag_offset.

    Bud positions/directions are NOT rotated — leaves read node bent positions
    directly (geom/leaves.py).

    Requires diameters to be set on all internodes (call update_diameters_incremental
    or compute_radii first).
    """
    # Always reset: a disabled sag must clear any previous offsets, and an
    # enabled sag must compute from scratch (idempotence).
    _reset_offsets(tree)
    if not cfg.enabled:
        return

    g = np.asarray(cfg.direction, dtype=np.float64)
    g_norm = norm3(g)
    if g_norm < 1e-12:
        return
    g = g / g_norm

    max_bend_rad = math.radians(float(cfg.max_bend_deg))
    rigid_order = int(cfg.rigid_axis_order)
    k = float(cfg.k)

    load_below = _compute_load_below(tree)

    stack: list[tuple[Node, int]] = [(tree.root, 0)]
    while stack:
        parent, parent_order = stack.pop()
        parent_bent = parent.position + parent.sag_offset
        for iod in parent.children_internodes:
            child = iod.child_node
            child_order = parent_order if iod.is_main_axis else parent_order + 1

            if child_order < rigid_order:
                stack.append((child, child_order))
                continue

            child_bent = child.position + child.sag_offset
            old_vec = child_bent - parent_bent
            seg_len = norm3(old_vec)
            if seg_len < 1e-12:
                stack.append((child, child_order))
                continue
            direction = old_vec / seg_len

            cross = cross3(direction, g)
            sin_theta = norm3(cross)
            if sin_theta < 1e-9:
                stack.append((child, child_order))
                continue
            axis = cross / sin_theta

            diameter = max(float(iod.diameter), 1e-4)
            r_iod = 0.5 * float(iod.diameter)
            iod_vol = math.pi * r_iod * r_iod * float(iod.length)
            load = iod_vol + float(load_below.get(id(child), 0.0))
            bend = k * load * sin_theta / (diameter * diameter)
            if bend > max_bend_rad:
                bend = max_bend_rad
            if bend <= 0.0:
                stack.append((child, child_order))
                continue

            R = _rodrigues(axis, bend)
            _rotate_subtree_offsets(child, R, parent_bent)
            stack.append((child, child_order))


def _compute_load_below(tree: Tree) -> dict[int, float]:
    """Wood volume in each node's subtree (sum of every internode growing out
    of it, recursively). Excludes the iod that leads INTO the node — callers
    that need that contribution add it inline. Keyed by id(node). Iterative
    post-order."""
    order: list[Node] = []
    stack: list[Node] = [tree.root]
    while stack:
        n = stack.pop()
        order.append(n)
        for iod in n.children_internodes:
            stack.append(iod.child_node)

    load: dict[int, float] = {}
    for n in reversed(order):
        total = 0.0
        for iod in n.children_internodes:
            child_load = load.get(id(iod.child_node), 0.0)
            # Volume of this internode itself: π * r² * L
            r = 0.5 * float(iod.diameter)
            iod_vol = math.pi * r * r * float(iod.length)
            total += iod_vol + child_load
        load[id(n)] = total
    return load


def _reset_offsets(tree: Tree) -> None:
    """Zero every Node.sag_offset in the tree (iterative DFS)."""
    stack: list[Node] = [tree.root]
    while stack:
        n = stack.pop()
        n.sag_offset = np.zeros(3, dtype=np.float64)
        for iod in n.children_internodes:
            stack.append(iod.child_node)


def _rotate_subtree_offsets(
    root: Node, R: np.ndarray, pivot: np.ndarray,
) -> None:
    """For every node in the subtree rooted at ``root`` (including ``root``),
    rotate its current bent position (position + sag_offset) by R around
    ``pivot`` and store the resulting offset back into sag_offset.

    Bud positions/directions are NOT touched — leaves read node bent positions
    in geom/leaves.py.
    """
    # Collect the subtree nodes in stack-walk order, stacking their current bent
    # positions (position + sag_offset) for one vectorized rotation pass.
    nodes: list[Node] = []
    bent_rows: list[np.ndarray] = []
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        nodes.append(node)
        bent_rows.append(node.position + node.sag_offset)
        for iod in node.children_internodes:
            stack.append(iod.child_node)

    P = np.asarray(bent_rows, dtype=np.float64)  # (M, 3)
    d = P - pivot
    dx = d[:, 0]
    dy = d[:, 1]
    dz = d[:, 2]
    NB = np.empty_like(P)
    # EXPLICIT-COLUMN form — bit-identical to per-row R @ v. Matmul (P-pivot)@R.T
    # is NOT bit-identical (BLAS reassociates the sum) and is forbidden.
    NB[:, 0] = R[0, 0] * dx + R[0, 1] * dy + R[0, 2] * dz + pivot[0]
    NB[:, 1] = R[1, 0] * dx + R[1, 1] * dy + R[1, 2] * dz + pivot[1]
    NB[:, 2] = R[2, 0] * dx + R[2, 1] * dy + R[2, 2] * dz + pivot[2]

    for i, node in enumerate(nodes):
        node.sag_offset = NB[i] - node.position


def _rodrigues(axis: np.ndarray, angle: float) -> np.ndarray:
    """3×3 rotation matrix around unit ``axis`` by ``angle`` radians."""
    c = math.cos(angle)
    s = math.sin(angle)
    one_c = 1.0 - c
    x, y, z = float(axis[0]), float(axis[1]), float(axis[2])
    return np.array([
        [c + x * x * one_c,     x * y * one_c - z * s, x * z * one_c + y * s],
        [y * x * one_c + z * s, c + y * y * one_c,     y * z * one_c - x * s],
        [z * x * one_c - y * s, z * y * one_c + x * s, c + z * z * one_c    ],
    ], dtype=np.float64)
