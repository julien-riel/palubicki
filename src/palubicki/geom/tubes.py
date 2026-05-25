# src/palubicki/geom/tubes.py
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from palubicki.geom.mesh import Material, Primitive
from palubicki.sim.tree import Node, Tree


@dataclass
class _ChainBuild:
    nodes: list[Node]
    radii: list[float]


def build_bark_primitive(tree: Tree, *, ring_sides: int, material: Material) -> Primitive:
    chains = _collect_chains(tree)

    positions: list[np.ndarray] = []
    normals: list[np.ndarray] = []
    uvs: list[np.ndarray] = []
    indices: list[int] = []

    for chain in chains:
        _emit_chain_tube(chain, ring_sides, positions, normals, uvs, indices)

    # Cap root: only the main trunk's first ring
    if chains:
        _emit_root_cap(chains[0], ring_sides, positions, normals, uvs, indices)

    pos_arr = np.asarray(positions, dtype=np.float32) if positions else np.zeros((0, 3), dtype=np.float32)
    nor_arr = np.asarray(normals, dtype=np.float32) if normals else np.zeros((0, 3), dtype=np.float32)
    uv_arr = np.asarray(uvs, dtype=np.float32) if uvs else np.zeros((0, 2), dtype=np.float32)
    idx_arr = np.asarray(indices, dtype=np.uint32) if indices else np.zeros((0,), dtype=np.uint32)

    return Primitive(positions=pos_arr, normals=nor_arr, uvs=uv_arr, indices=idx_arr, material=material)


def _collect_chains(tree: Tree) -> list[_ChainBuild]:
    chains: list[_ChainBuild] = []
    _walk_chains(tree.root, current=None, chains=chains)
    # Ensure trunk-from-root chain is first
    return chains


def _walk_chains(node: Node, current: _ChainBuild | None, chains: list[_ChainBuild]) -> None:
    if current is None:
        current = _ChainBuild(nodes=[node], radii=[_avg_radius_at_node(node)])
        chains.append(current)
    else:
        current.nodes.append(node)
        current.radii.append(_avg_radius_at_node(node))

    main = next((iod for iod in node.children_internodes if iod.is_main_axis), None)
    laterals = [iod for iod in node.children_internodes if not iod.is_main_axis]

    if main is not None:
        _walk_chains(main.child_node, current, chains)
    for lat in laterals:
        # Start a NEW chain at the parent node so the lateral tube anchors here.
        new_chain = _ChainBuild(
            nodes=[node, lat.child_node],
            radii=[lat.diameter / 2.0, _avg_radius_at_node(lat.child_node)],
        )
        chains.append(new_chain)
        _walk_chains_continue(lat.child_node, new_chain, chains)


def _walk_chains_continue(node: Node, current: _ChainBuild, chains: list[_ChainBuild]) -> None:
    main = next((iod for iod in node.children_internodes if iod.is_main_axis), None)
    laterals = [iod for iod in node.children_internodes if not iod.is_main_axis]
    if main is not None:
        current.nodes.append(main.child_node)
        current.radii.append(_avg_radius_at_node(main.child_node))
        _walk_chains_continue(main.child_node, current, chains)
    for lat in laterals:
        new_chain = _ChainBuild(
            nodes=[node, lat.child_node],
            radii=[lat.diameter / 2.0, _avg_radius_at_node(lat.child_node)],
        )
        chains.append(new_chain)
        _walk_chains_continue(lat.child_node, new_chain, chains)


def _avg_radius_at_node(node: Node) -> float:
    rs: list[float] = []
    if node.parent_internode is not None:
        rs.append(node.parent_internode.diameter / 2.0)
    for iod in node.children_internodes:
        if iod.is_main_axis:
            rs.append(iod.diameter / 2.0)
            break
    if not rs:
        return 0.0
    return sum(rs) / len(rs)


def _emit_chain_tube(
    chain: _ChainBuild,
    ring_sides: int,
    positions: list,
    normals: list,
    uvs: list,
    indices: list,
) -> None:
    if len(chain.nodes) < 2:
        return

    columns = ring_sides + 1  # seam duplicated for clean UVs

    # Build tangents per node
    tangents = _compute_tangents([n.position for n in chain.nodes])

    # Parallel transport frame
    t0 = tangents[0]
    canonical = np.array([1.0, 0.0, 0.0]) if abs(t0[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    right = canonical - np.dot(canonical, t0) * t0
    right = right / np.linalg.norm(right)
    up = np.cross(t0, right)

    start_vertex = len(positions)
    cum_length = 0.0
    prev_pos: np.ndarray | None = None

    for i, (node, r) in enumerate(zip(chain.nodes, chain.radii)):
        if i > 0:
            cum_length += float(np.linalg.norm(node.position - prev_pos))
            new_t = tangents[i]
            old_t = tangents[i - 1]
            right, up = _transport_frame(right, up, old_t, new_t)
        for k in range(columns):
            angle = 2.0 * math.pi * (k % ring_sides) / ring_sides
            radial = math.cos(angle) * right + math.sin(angle) * up
            positions.append(node.position + r * radial)
            normals.append(radial)
            u = k / ring_sides
            v = cum_length
            uvs.append(np.array([u, v], dtype=np.float32))
        prev_pos = node.position

    # Quads between consecutive rings
    for i in range(len(chain.nodes) - 1):
        ring0 = start_vertex + i * columns
        ring1 = start_vertex + (i + 1) * columns
        for k in range(ring_sides):
            a = ring0 + k
            b = ring1 + k
            c = ring1 + k + 1
            d = ring0 + k + 1
            indices.extend([a, b, c, a, c, d])


def _emit_root_cap(
    chain: _ChainBuild,
    ring_sides: int,
    positions: list,
    normals: list,
    uvs: list,
    indices: list,
) -> None:
    # Bottom of trunk: fan from center down.
    # If the trunk chain has <2 nodes, _emit_chain_tube did not emit a ring,
    # so referencing ring0 vertices here would produce OOB indices.
    if len(chain.nodes) < 2:
        return
    columns = ring_sides + 1
    center = chain.nodes[0].position.copy()
    center_index = len(positions)
    positions.append(center)
    normals.append(np.array([0.0, -1.0, 0.0]))
    uvs.append(np.array([0.5, 0.5], dtype=np.float32))
    # The chain's first ring was emitted at indices [start..start+columns-1]
    # We need its start: it's the very first ring written for this chain.
    # Assume the chain is the first one emitted (trunk), so start = 0.
    # For safety, re-derive: ring 0 = first `columns` vertices of this chain.
    # In our emission order, chain[0] starts at position index 0 (called first).
    ring0_start = 0
    for k in range(ring_sides):
        a = ring0_start + k
        b = ring0_start + k + 1
        indices.extend([center_index, b, a])


def _compute_tangents(positions: list[np.ndarray]) -> list[np.ndarray]:
    tangents: list[np.ndarray] = []
    for i, p in enumerate(positions):
        if i == 0:
            t = positions[1] - p
        elif i == len(positions) - 1:
            t = p - positions[i - 1]
        else:
            t = positions[i + 1] - positions[i - 1]
        n = np.linalg.norm(t)
        tangents.append(t / n if n > 1e-12 else np.array([0.0, 1.0, 0.0]))
    return tangents


def _transport_frame(
    right: np.ndarray, up: np.ndarray, old_t: np.ndarray, new_t: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    dot = float(np.clip(np.dot(old_t, new_t), -1.0, 1.0))
    if dot > 0.999999:
        return right, up
    axis = np.cross(old_t, new_t)
    n = np.linalg.norm(axis)
    if n < 1e-12:
        return right, up
    axis = axis / n
    angle = math.acos(dot)
    new_right = _rotate_vec(right, axis, angle)
    new_up = _rotate_vec(up, axis, angle)
    return new_right, new_up


def _rotate_vec(v: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    cos_a = math.cos(angle); sin_a = math.sin(angle)
    return (v * cos_a + np.cross(axis, v) * sin_a + axis * np.dot(axis, v) * (1 - cos_a))
