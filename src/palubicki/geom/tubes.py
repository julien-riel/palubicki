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


@dataclass
class _FlareSpec:
    """Render-time flare descriptor for the trunk chain. Ground reference is the
    chain's own first-node Y (computed inside ``_emit_chain_tube``)."""
    height: float
    factor: float            # already jittered + clamped to >= 1.0 by build_bark_primitive
    falloff: str             # "linear" | "smoothstep"
    buttress_count: int
    buttress_amplitude: float
    buttress_phase: float


def _falloff(t: np.ndarray, mode: str) -> np.ndarray:
    """Flare blend weight on ``t`` in [0, 1] (1 at base, 0 at top of flare zone).

    ``linear`` is identity; ``smoothstep`` is the classic ``3t^2 - 2t^3``.
    """
    if mode == "smoothstep":
        return t * t * (3.0 - 2.0 * t)
    return t


def build_bark_primitive(
    tree: Tree,
    *,
    ring_sides: int,
    material: Material,
    flare_height: float = 0.0,
    flare_factor: float = 1.0,
    flare_falloff: str = "linear",
    buttress_count: int = 0,
    buttress_amplitude: float = 0.0,
    flare_variation: float = 0.0,
    seed: int = 0,
) -> Primitive:
    chains = _collect_chains(tree)

    # Per-tree variation: phase rotates buttress ridges, jitter perturbs the factor.
    # Two draws in fixed order keep seed -> output deterministic.
    rng = np.random.default_rng(seed)
    buttress_phase = float(rng.uniform(0.0, 2.0 * np.pi))
    jitter = float(rng.uniform(-1.0, 1.0)) * flare_variation
    eff_factor = max(1.0, flare_factor * (1.0 + jitter))

    flare = _FlareSpec(
        height=flare_height,
        factor=eff_factor,
        falloff=flare_falloff,
        buttress_count=buttress_count,
        buttress_amplitude=buttress_amplitude,
        buttress_phase=buttress_phase,
    )

    pos_parts: list[np.ndarray] = []
    nor_parts: list[np.ndarray] = []
    uv_parts: list[np.ndarray] = []
    idx_parts: list[np.ndarray] = []
    vertex_offset = 0

    for i, chain in enumerate(chains):
        chain_flare = flare if i == 0 else None  # trunk chain only
        p, n, u, idx = _emit_chain_tube(chain, ring_sides, vertex_offset, chain_flare)
        if p.shape[0]:
            pos_parts.append(p)
            nor_parts.append(n)
            uv_parts.append(u)
            idx_parts.append(idx)
            vertex_offset += p.shape[0]

    # Cap root: only the main trunk's first ring
    if chains:
        p, n, u, idx = _emit_root_cap(chains[0], ring_sides, vertex_offset)
        if p.shape[0]:
            pos_parts.append(p)
            nor_parts.append(n)
            uv_parts.append(u)
            idx_parts.append(idx)
            vertex_offset += p.shape[0]

    pos_arr = (np.concatenate(pos_parts, axis=0).astype(np.float32, copy=False)
               if pos_parts else np.zeros((0, 3), dtype=np.float32))
    nor_arr = (np.concatenate(nor_parts, axis=0).astype(np.float32, copy=False)
               if nor_parts else np.zeros((0, 3), dtype=np.float32))
    uv_arr = (np.concatenate(uv_parts, axis=0)
              if uv_parts else np.zeros((0, 2), dtype=np.float32))
    idx_arr = (np.concatenate(idx_parts, axis=0).astype(np.uint32, copy=False)
               if idx_parts else np.zeros((0,), dtype=np.uint32))

    return Primitive(positions=pos_arr, normals=nor_arr, uvs=uv_arr, indices=idx_arr, material=material)


def _collect_chains(tree: Tree) -> list[_ChainBuild]:
    """Iterative collection of tube chains from the tree.

    The trunk chain starts at the root and follows main-axis children.
    Each lateral branching point starts a new chain anchored at the parent node.
    """
    chains: list[_ChainBuild] = []

    # Stack carries (node, current_chain, is_chain_start).
    # is_chain_start=True: we are starting a brand new chain from this node (root or lateral root).
    # is_chain_start=False: we are continuing an existing chain (following main axis).
    root = tree.root
    root_chain = _ChainBuild(nodes=[root], radii=[_avg_radius_at_node(root)])
    chains.append(root_chain)

    # Stack entries: (node, chain) — node has already been appended to chain.
    stack: list[tuple[Node, _ChainBuild]] = [(root, root_chain)]

    while stack:
        node, current = stack.pop()

        main = next((iod for iod in node.children_internodes if iod.is_main_axis), None)
        laterals = [iod for iod in node.children_internodes if not iod.is_main_axis]

        # Extend current chain with main-axis child
        if main is not None:
            current.nodes.append(main.child_node)
            current.radii.append(_avg_radius_at_node(main.child_node))
            stack.append((main.child_node, current))

        # Start new chains for laterals
        for lat in laterals:
            new_chain = _ChainBuild(
                nodes=[node, lat.child_node],
                radii=[lat.diameter / 2.0, _avg_radius_at_node(lat.child_node)],
            )
            chains.append(new_chain)
            stack.append((lat.child_node, new_chain))

    return chains


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


def _flare_radius_field(
    node_positions: np.ndarray,   # (N, 3) bent positions
    radii_arr: np.ndarray,        # (N,)
    angles: np.ndarray,           # (columns,)
    flare: _FlareSpec | None,
) -> np.ndarray:
    """Effective per-vertex radius. ``(N, 1)`` (broadcasts over columns) when no
    flare, ``(N, columns)`` when the trunk chain carries a ``_FlareSpec``.

    Radial (axisymmetric) component only is added here; buttress is layered on in
    a later task. Ground reference is the chain's own first node ``node_positions[0, 1]``.
    """
    if flare is None or flare.height <= 0.0:
        return radii_arr[:, None]

    base_y = node_positions[0, 1]
    y = node_positions[:, 1] - base_y                         # (N,)
    t = np.clip((flare.height - y) / flare.height, 0.0, 1.0)  # 1 at base, 0 at top
    f = _falloff(t, flare.falloff)                            # (N,)
    radial = 1.0 + (flare.factor - 1.0) * f                   # (N,)
    return (radii_arr * radial)[:, None]                      # (N, 1)


def _emit_chain_tube(
    chain: _ChainBuild,
    ring_sides: int,
    vertex_offset: int,
    flare: _FlareSpec | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Emit a tube along ``chain``. Returns ``(positions, normals, uvs, indices)``.

    Vectorised column expansion: parallel-transport frame is propagated node-by-node
    (inherently sequential), then the per-node ring of ``columns = ring_sides + 1``
    vertices is built by numpy broadcasting in one shot — replacing the original
    ``for k in range(columns)`` Python loop.

    Returned ``indices`` are already shifted by ``vertex_offset`` for direct
    concatenation by the caller.
    """
    n_nodes = len(chain.nodes)
    if n_nodes < 2:
        return (
            np.zeros((0, 3), dtype=np.float64),
            np.zeros((0, 3), dtype=np.float64),
            np.zeros((0, 2), dtype=np.float32),
            np.zeros((0,), dtype=np.int64),
        )

    columns = ring_sides + 1  # seam duplicated for clean UVs

    node_positions = np.asarray(
        [n.position + n.sag_offset for n in chain.nodes], dtype=np.float64
    )  # (N, 3)  — bent positions; sag_offset is np.zeros(3) when sag disabled
    radii_arr = np.asarray(chain.radii, dtype=np.float64)  # (N,)

    tangents = _compute_tangents(node_positions)  # (N, 3)

    # Parallel-transport frame — sequential across nodes, vectorised across columns.
    rights = np.empty((n_nodes, 3), dtype=np.float64)
    ups = np.empty((n_nodes, 3), dtype=np.float64)
    t0 = tangents[0]
    canonical = np.array([1.0, 0.0, 0.0]) if abs(t0[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    right = canonical - np.dot(canonical, t0) * t0
    right = right / np.linalg.norm(right)
    rights[0] = right
    ups[0] = _cross3(t0, right)
    for i in range(1, n_nodes):
        rights[i], ups[i] = _transport_frame(rights[i - 1], ups[i - 1], tangents[i - 1], tangents[i])

    # Cumulative arc length per node (matches the original ``cum_length += ‖Δp‖`` accumulation).
    seg_lens = np.zeros(n_nodes, dtype=np.float64)
    seg_lens[1:] = np.linalg.norm(node_positions[1:] - node_positions[:-1], axis=1)
    cum_lengths = np.cumsum(seg_lens)

    # Per-column angles. ``k % ring_sides`` makes column ``ring_sides`` reuse angle 0
    # so the seam vertex sits bit-exactly on top of column 0 in 3D.
    k_indices = np.arange(columns)
    angles = 2.0 * np.pi * (k_indices % ring_sides) / ring_sides
    cos_a = np.cos(angles)  # (columns,)
    sin_a = np.sin(angles)  # (columns,)

    # radials[i, k] = cos_a[k] * rights[i] + sin_a[k] * ups[i]  →  (N, columns, 3)
    radials = cos_a[None, :, None] * rights[:, None, :] + sin_a[None, :, None] * ups[:, None, :]
    r_eff = _flare_radius_field(node_positions, radii_arr, angles, flare)
    positions = node_positions[:, None, :] + r_eff[:, :, None] * radials
    normals = radials  # already unit length: |cos²+sin²|·|right⊥up|=1

    u_row = k_indices.astype(np.float32) / np.float32(ring_sides)
    uvs = np.empty((n_nodes, columns, 2), dtype=np.float32)
    uvs[..., 0] = u_row[None, :]
    uvs[..., 1] = cum_lengths.astype(np.float32)[:, None]

    positions_flat = positions.reshape(n_nodes * columns, 3)
    normals_flat = normals.reshape(n_nodes * columns, 3)
    uvs_flat = uvs.reshape(n_nodes * columns, 2)

    # Vectorised quad indices: per segment i, per side k, emit two tris [a,b,c,a,c,d]
    # with a = ring0+k, b = ring1+k, c = ring1+k+1, d = ring0+k+1.
    n_seg = n_nodes - 1
    i_arr = np.arange(n_seg)
    k_arr = np.arange(ring_sides)
    ring0 = vertex_offset + i_arr[:, None] * columns          # (n_seg, 1)
    ring1 = vertex_offset + (i_arr[:, None] + 1) * columns
    a = ring0 + k_arr[None, :]
    b = ring1 + k_arr[None, :]
    c = ring1 + k_arr[None, :] + 1
    d = ring0 + k_arr[None, :] + 1
    indices = np.stack([a, b, c, a, c, d], axis=-1).reshape(-1).astype(np.int64)

    return positions_flat, normals_flat, uvs_flat, indices


def _emit_root_cap(
    chain: _ChainBuild,
    ring_sides: int,
    vertex_offset: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Bottom-of-trunk fan: one center vertex + ``ring_sides`` triangles.

    Triangles assume the trunk's first ring is at global indices [0..columns-1] —
    i.e., the trunk chain was emitted first by ``build_bark_primitive``.

    When the trunk chain had < 2 nodes, no ring exists; the center vertex is still
    emitted (legacy behavior) but no triangles are issued.
    """
    center = (chain.nodes[0].position + chain.nodes[0].sag_offset).astype(np.float64)
    positions = center[None, :]                                       # (1, 3)
    normals = np.array([[0.0, -1.0, 0.0]], dtype=np.float64)          # (1, 3)
    uvs = np.array([[0.5, 0.5]], dtype=np.float32)                    # (1, 2)

    if len(chain.nodes) < 2:
        return positions, normals, uvs, np.zeros((0,), dtype=np.int64)

    ring0_start = 0
    center_index = vertex_offset
    k_arr = np.arange(ring_sides)
    a = ring0_start + k_arr
    b = ring0_start + k_arr + 1
    centers = np.full_like(a, center_index)
    indices = np.stack([centers, b, a], axis=-1).reshape(-1).astype(np.int64)
    return positions, normals, uvs, indices


def _compute_tangents(positions: np.ndarray) -> np.ndarray:
    """Vectorised central-difference tangents. ``positions``: ``(N, 3)`` → ``(N, 3)``,
    unit-normalised. Endpoints use forward/backward difference; degenerate (zero-norm)
    rows fall back to ``(0, 1, 0)`` (matching the scalar version's behavior)."""
    n = positions.shape[0]
    if n < 2:
        out = np.empty((n, 3), dtype=np.float64)
        if n == 1:
            out[0] = (0.0, 1.0, 0.0)
        return out
    t = np.empty_like(positions)
    t[0] = positions[1] - positions[0]
    t[-1] = positions[-1] - positions[-2]
    if n > 2:
        t[1:-1] = positions[2:] - positions[:-2]
    norms = np.linalg.norm(t, axis=1)
    safe = norms > 1e-12
    t[safe] /= norms[safe, None]
    t[~safe] = (0.0, 1.0, 0.0)
    return t


def _transport_frame(
    right: np.ndarray, up: np.ndarray, old_t: np.ndarray, new_t: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    dot = float(np.clip(np.dot(old_t, new_t), -1.0, 1.0))
    if dot > 0.999999:
        return right, up
    axis = _cross3(old_t, new_t)
    n = np.linalg.norm(axis)
    if n < 1e-12:
        return right, up
    axis = axis / n
    angle = math.acos(dot)
    new_right = _rotate_vec(right, axis, angle)
    new_up = _rotate_vec(up, axis, angle)
    return new_right, new_up


def _rotate_vec(v: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    return (v * cos_a + _cross3(axis, v) * sin_a + axis * np.dot(axis, v) * (1 - cos_a))


def _cross3(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    # np.cross has ~25 µs overhead per call for 3-vectors due to axis handling.
    # Inlined math drops that to ~1 µs, dominating the chain-tube build.
    return np.array([
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ])
