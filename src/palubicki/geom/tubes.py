# src/palubicki/geom/tubes.py
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from palubicki.geom.bark_blend import BarkBlendStops, bark_tint
from palubicki.geom.mesh import Material, Primitive
from palubicki.geom.wind import WindCalibration, branch_phase, branch_phase_series, calibrate
from palubicki.geom.wind import tier as wind_tier_of
from palubicki.sim.tree import Node, Tree


@dataclass
class _ChainBuild:
    nodes: list[Node]
    radii: list[float]
    # Topological axis order of this chain (trunk = 0, each lateral nesting +1).
    # Drives the wind tier stamped on the chain's vertices (geom/wind.py).
    axis_order: int = 0


@dataclass
class _TubeArrays:
    """One tube chain (or root cap) emitted as flat per-vertex arrays. ``wind`` /
    ``pivot`` / ``wind_tier`` / ``tangents`` carry the portable wind contract;
    ``tint`` is the optional bark-age COLOR_1."""
    positions: np.ndarray
    normals: np.ndarray
    uvs: np.ndarray
    indices: np.ndarray
    tint: np.ndarray | None
    wind: np.ndarray
    pivot: np.ndarray
    wind_tier: np.ndarray
    tangents: np.ndarray


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
    stops: BarkBlendStops | None = None,
    calibration: WindCalibration | None = None,
) -> Primitive:
    chains = _collect_chains(tree)
    cal = calibration if calibration is not None else calibrate(tree)
    # Phase is hashed relative to the collar so identical trees stay instance-shareable.
    origin = np.asarray(tree.root.position, dtype=np.float64)

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

    parts: list[_TubeArrays] = []
    vertex_offset = 0

    for i, chain in enumerate(chains):
        chain_flare = flare if i == 0 else None  # trunk chain only
        part = _emit_chain_tube(chain, ring_sides, vertex_offset, cal, origin, chain_flare, stops)
        if part.positions.shape[0]:
            parts.append(part)
            vertex_offset += part.positions.shape[0]

    # Cap root: only the main trunk's first ring
    if chains:
        cap = _emit_root_cap(chains[0], ring_sides, vertex_offset, cal, origin, stops)
        if cap.positions.shape[0]:
            parts.append(cap)
            vertex_offset += cap.positions.shape[0]

    def _cat(attr: str, width: int, dtype) -> np.ndarray:
        arrs = [getattr(p, attr) for p in parts]
        if not arrs:
            shape = (0,) if width == 1 else (0, width)
            return np.zeros(shape, dtype=dtype)
        return np.concatenate(arrs, axis=0).astype(dtype, copy=False)

    pos_arr = _cat("positions", 3, np.float32)
    nor_arr = _cat("normals", 3, np.float32)
    uv_arr = _cat("uvs", 2, np.float32)
    idx_arr = _cat("indices", 1, np.uint32)
    wind_arr = _cat("wind", 3, np.float32)
    pivot_arr = _cat("pivot", 3, np.float32)
    tier_arr = _cat("wind_tier", 1, np.float32)
    tan_arr = _cat("tangents", 4, np.float32)
    # Tint (bark-age COLOR_1) is only present when blend stops are configured;
    # every part agrees (all None or all set), so check the first.
    tint_arr = None
    if parts and parts[0].tint is not None:
        tint_arr = np.concatenate([p.tint for p in parts], axis=0).astype(np.float32, copy=False)

    return Primitive(positions=pos_arr, normals=nor_arr, uvs=uv_arr, indices=idx_arr,
                     material=material, tint=tint_arr, wind=wind_arr, pivot=pivot_arr,
                     wind_tier=tier_arr, tangents=tan_arr)


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
    root_chain = _ChainBuild(nodes=[root], radii=[_avg_radius_at_node(root)], axis_order=0)
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

        # Start new chains for laterals — each is one axis order deeper than the
        # axis it branches off, which becomes its wind tier.
        for lat in laterals:
            new_chain = _ChainBuild(
                nodes=[node, lat.child_node],
                radii=[lat.diameter / 2.0, _avg_radius_at_node(lat.child_node)],
                axis_order=current.axis_order + 1,
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
    """Effective per-vertex radius field.

    Returns ``(N, 1)`` when there is no buttress (or no flare) so it broadcasts
    over columns; returns ``(N, columns)`` when azimuthal buttress ridges are
    active.  Ground reference is the chain's own first node
    ``node_positions[0, 1]``.

    The ``angles`` array uses ``k % ring_sides`` upstream so
    ``angles[ring_sides] == angles[0]``; the duplicated seam column therefore
    receives the same buttress modulation as column 0, keeping the seam welded.
    """
    if flare is None or flare.height <= 0.0:
        return radii_arr[:, None]

    base_y = node_positions[0, 1]
    y = node_positions[:, 1] - base_y                         # (N,)
    t = np.clip((flare.height - y) / flare.height, 0.0, 1.0)  # 1 at base, 0 at top
    blend = _falloff(t, flare.falloff)                         # (N,)
    radial = 1.0 + (flare.factor - 1.0) * blend               # (N,)

    if flare.buttress_count <= 0 or flare.buttress_amplitude <= 0.0:
        return (radii_arr * radial)[:, None]                   # (N, 1)

    # Azimuthal ridges, fading with the same falloff so they live only in the collar.
    # ``angles`` uses ``k % ring_sides`` upstream, so angles[ring_sides] == angles[0]
    # and the duplicated seam vertex therefore stays welded.
    butt = 1.0 + flare.buttress_amplitude * blend[:, None] * np.cos(
        flare.buttress_count * angles[None, :] + flare.buttress_phase
    )                                                          # (N, columns)
    return radii_arr[:, None] * radial[:, None] * butt         # (N, columns)


def _emit_chain_tube(
    chain: _ChainBuild,
    ring_sides: int,
    vertex_offset: int,
    cal: WindCalibration,
    origin: np.ndarray,
    flare: _FlareSpec | None = None,
    stops: BarkBlendStops | None = None,
) -> _TubeArrays:
    """Emit a tube along ``chain`` as a :class:`_TubeArrays`.

    Vectorised column expansion: parallel-transport frame is propagated node-by-node
    (inherently sequential), then the per-node ring of ``columns = ring_sides + 1``
    vertices is built by numpy broadcasting in one shot — replacing the original
    ``for k in range(columns)`` Python loop.

    Wind contract stamped here (geom/wind.py): each vertex carries ``COLOR_0 =
    (phase, stiffness, 0)`` — phase is a travelling wave from the axis base
    (``node_positions[0]``, also the branch pivot) toward the tip, stiffness comes
    from the node's diameter calibrated to the tree; ``pivot`` is the axis base
    broadcast across the chain; ``wind_tier`` is the chain's axis order. ``TANGENT``
    is the azimuthal direction of the parallel-transport frame (the surface
    tangent that follows the +U bark wrap), handedness +1 — previously discarded.

    Returned ``indices`` are already shifted by ``vertex_offset`` for direct
    concatenation by the caller.
    """
    n_nodes = len(chain.nodes)
    if n_nodes < 2:
        return _TubeArrays(
            positions=np.zeros((0, 3), dtype=np.float64),
            normals=np.zeros((0, 3), dtype=np.float64),
            uvs=np.zeros((0, 2), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.int64),
            tint=(np.zeros((0, 3), dtype=np.float32) if stops is not None else None),
            wind=np.zeros((0, 3), dtype=np.float32),
            pivot=np.zeros((0, 3), dtype=np.float32),
            wind_tier=np.zeros((0,), dtype=np.float32),
            tangents=np.zeros((0, 4), dtype=np.float32),
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

    # Surface tangent for normal mapping (P2): the azimuthal direction d(pos)/d(angle)
    # = -sin·right + cos·up, which follows the +U bark wrap. Right-handed with the
    # radial normal and the +V (along-tube) direction, so MikkTSpace handedness is +1.
    tangent_dir = (-sin_a[None, :, None] * rights[:, None, :]
                   + cos_a[None, :, None] * ups[:, None, :])     # (N, columns, 3)
    tangents = np.empty((n_nodes, columns, 4), dtype=np.float64)
    tangents[..., :3] = tangent_dir
    tangents[..., 3] = 1.0

    # Wind contract. phase = travelling wave from the axis base; stiffness from the
    # per-node diameter calibrated to the tree; leafMask = 0 for wood.
    base_pos = node_positions[0]                                  # bent axis base = branch pivot
    # Phase identity is the *structural* (pre-sag) axis base, tree-relative — stable
    # under sag toggling and shareable across identical trees. Single formula in wind.py.
    phases = branch_phase_series(chain.nodes[0].position, n_nodes, origin)   # (N,)
    span = cal.d_max - cal.d_min
    if span <= 1e-9:
        stiff = np.ones(n_nodes, dtype=np.float64)
    else:
        stiff = np.clip((2.0 * radii_arr - cal.d_min) / span, 0.0, 1.0)
    wind_node = np.stack([phases, stiff, np.zeros(n_nodes)], axis=1)     # (N, 3)
    wind = np.broadcast_to(wind_node[:, None, :], (n_nodes, columns, 3))
    pivot = np.broadcast_to(base_pos[None, None, :], (n_nodes, columns, 3))
    tier_val = float(wind_tier_of(chain.axis_order))
    wind_tier = np.full((n_nodes, columns), tier_val, dtype=np.float64)

    positions_flat = positions.reshape(n_nodes * columns, 3)
    normals_flat = normals.reshape(n_nodes * columns, 3)
    uvs_flat = uvs.reshape(n_nodes * columns, 2)
    tangents_flat = tangents.reshape(n_nodes * columns, 4)
    wind_flat = np.ascontiguousarray(wind.reshape(n_nodes * columns, 3), dtype=np.float32)
    pivot_flat = np.ascontiguousarray(pivot.reshape(n_nodes * columns, 3), dtype=np.float32)
    tier_flat = wind_tier.reshape(n_nodes * columns)

    # Vectorised quad indices: per segment i, per side k, emit two tris [a,c,b,a,d,c]
    # with a = ring0+k, b = ring1+k, c = ring1+k+1, d = ring0+k+1. This winding is
    # CCW as seen from outside (glTF 2.0 §3.7.2 front face), agreeing with the outward
    # radial normals so single-sided bark survives back-face culling (#33).
    n_seg = n_nodes - 1
    i_arr = np.arange(n_seg)
    k_arr = np.arange(ring_sides)
    ring0 = vertex_offset + i_arr[:, None] * columns          # (n_seg, 1)
    ring1 = vertex_offset + (i_arr[:, None] + 1) * columns
    a = ring0 + k_arr[None, :]
    b = ring1 + k_arr[None, :]
    c = ring1 + k_arr[None, :] + 1
    d = ring0 + k_arr[None, :] + 1
    indices = np.stack([a, c, b, a, d, c], axis=-1).reshape(-1).astype(np.int64)

    tint_flat = None
    if stops is not None:
        # Per-node diameter = 2 * radius; broadcast each node's tint across the ring.
        diameters = 2.0 * radii_arr                                  # (N,)
        node_rgb = bark_tint(diameters, stops)                       # (N, 3) float32
        tint = np.broadcast_to(node_rgb[:, None, :], (n_nodes, columns, 3))
        tint_flat = tint.reshape(n_nodes * columns, 3).astype(np.float32, copy=True)

    return _TubeArrays(
        positions=positions_flat, normals=normals_flat, uvs=uvs_flat, indices=indices,
        tint=tint_flat, wind=wind_flat, pivot=pivot_flat, wind_tier=tier_flat,
        tangents=tangents_flat,
    )


def _emit_root_cap(
    chain: _ChainBuild,
    ring_sides: int,
    vertex_offset: int,
    cal: WindCalibration,
    origin: np.ndarray,
    stops: BarkBlendStops | None = None,
) -> _TubeArrays:
    """Bottom-of-trunk fan: one center vertex + ``ring_sides`` triangles.

    Triangles assume the trunk's first ring is at global indices [0..columns-1] —
    i.e., the trunk chain was emitted first by ``build_bark_primitive``.

    When the trunk chain had < 2 nodes, no ring exists; the center vertex is still
    emitted (legacy behavior) but no triangles are issued. Wind-wise the cap is
    pure trunk: tier 0, pivot at the collar, leafMask 0.
    """
    center = (chain.nodes[0].position + chain.nodes[0].sag_offset).astype(np.float64)
    positions = center[None, :]                                       # (1, 3)
    normals = np.array([[0.0, -1.0, 0.0]], dtype=np.float64)          # (1, 3)
    uvs = np.array([[0.5, 0.5]], dtype=np.float32)                    # (1, 2)

    base_phase = branch_phase(chain.nodes[0].position, 0, origin)   # structural, ordinal 0
    base_stiff = cal.stiffness(2.0 * chain.radii[0])
    wind = np.array([[base_phase, base_stiff, 0.0]], dtype=np.float32)  # (1, 3)
    pivot = center[None, :].astype(np.float32)                          # (1, 3)
    tier = np.array([float(wind_tier_of(chain.axis_order))], dtype=np.float32)
    # Cap normal is (0,-1,0); any perpendicular is a valid tangent. +X, handedness +1.
    tangents = np.array([[1.0, 0.0, 0.0, 1.0]], dtype=np.float32)       # (1, 4)

    cap_tint = None
    if stops is not None:
        base_diameter = 2.0 * chain.radii[0]
        cap_tint = bark_tint(np.array([base_diameter]), stops).astype(np.float32)  # (1, 3)

    if len(chain.nodes) < 2:
        return _TubeArrays(
            positions=positions, normals=normals, uvs=uvs,
            indices=np.zeros((0,), dtype=np.int64),
            tint=cap_tint, wind=wind, pivot=pivot, wind_tier=tier, tangents=tangents,
        )

    ring0_start = 0
    center_index = vertex_offset
    k_arr = np.arange(ring_sides)
    a = ring0_start + k_arr
    b = ring0_start + k_arr + 1
    centers = np.full_like(a, center_index)
    # [center, b, a] already winds CCW-from-below, agreeing with the (0,-1,0) cap
    # normal — do NOT flip it alongside the walls (#33). The wall fix made the walls
    # match this cap's existing outward orientation, not the other way around.
    indices = np.stack([centers, b, a], axis=-1).reshape(-1).astype(np.int64)
    return _TubeArrays(
        positions=positions, normals=normals, uvs=uvs, indices=indices,
        tint=cap_tint, wind=wind, pivot=pivot, wind_tier=tier, tangents=tangents,
    )


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
