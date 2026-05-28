from __future__ import annotations

import math
from collections import defaultdict, deque
from typing import TYPE_CHECKING

import numpy as np

from palubicki.sim.tree import BudState, Internode, Node, Tree

if TYPE_CHECKING:
    from palubicki.config import Config


# ── Internal walkers ──────────────────────────────────────────────────────

def _walk_nodes(root: Node) -> list[Node]:
    out: list[Node] = []
    q: deque[Node] = deque([root])
    while q:
        n = q.popleft()
        out.append(n)
        for iod in n.children_internodes:
            q.append(iod.child_node)
    return out


def _walk_internodes(root: Node) -> list[Internode]:
    out: list[Internode] = []
    q: deque[Internode] = deque(root.children_internodes)
    while q:
        iod = q.popleft()
        out.append(iod)
        for c in iod.child_node.children_internodes:
            q.append(c)
    return out


# ── Strahler / Horton ─────────────────────────────────────────────────────

def _strahler_orders(root: Node) -> dict[int, int]:
    """Return {id(Internode): order}. Empty if root has no children."""
    orders: dict[int, int] = {}

    def visit(iod: Internode) -> int:
        kids = iod.child_node.children_internodes
        if not kids:
            order = 1
        else:
            child_orders = [visit(c) for c in kids]
            mx = max(child_orders)
            order = mx + 1 if child_orders.count(mx) > 1 else mx
        orders[id(iod)] = order
        return order

    for iod in root.children_internodes:
        visit(iod)
    return orders


def _strahler_metrics(root: Node) -> dict:
    orders = _strahler_orders(root)
    if not orders:
        return {
            "strahler_order_max": 0,
            "strahler_order_histogram": {},
            "horton_bifurcation_ratio": {},
            "horton_bifurcation_ratio_mean": float("nan"),
        }
    hist: dict[int, int] = defaultdict(int)
    for o in orders.values():
        hist[o] += 1
    hist_d = dict(sorted(hist.items()))
    order_max = max(hist_d)
    ratios: dict[int, float] = {}
    for n in range(1, order_max):
        if hist_d.get(n + 1, 0) > 0:
            ratios[n] = hist_d[n] / hist_d[n + 1]
    if ratios:
        # Geometric mean
        log_sum = sum(math.log(r) for r in ratios.values())
        ratio_mean = math.exp(log_sum / len(ratios))
    else:
        ratio_mean = float("nan")
    return {
        "strahler_order_max": order_max,
        "strahler_order_histogram": hist_d,
        "horton_bifurcation_ratio": ratios,
        "horton_bifurcation_ratio_mean": ratio_mean,
    }


# ── Topological axis order ────────────────────────────────────────────────

def _axis_orders(root: Node) -> dict[int, int]:
    """Return {id(Internode): axis_order} derived from is_main_axis topology.

    Internode has no axis_order field — only Bud does. We reconstruct it
    from the tree shape: the first internode from root is order 0; each
    main-axis continuation inherits its parent's order; each lateral
    (is_main_axis=False) gets parent + 1.
    """
    out: dict[int, int] = {}
    q: deque[Internode] = deque(root.children_internodes)
    while q:
        iod = q.popleft()
        parent_iod = iod.parent_node.parent_internode
        if parent_iod is None:
            out[id(iod)] = 0
        else:
            base = out[id(parent_iod)]
            out[id(iod)] = base if iod.is_main_axis else base + 1
        for c in iod.child_node.children_internodes:
            q.append(c)
    return out


# ── Geometry helpers ──────────────────────────────────────────────────────

def _tangent(iod: Internode) -> np.ndarray:
    v = np.asarray(iod.child_node.position - iod.parent_node.position,
                   dtype=np.float64)
    n = float(np.linalg.norm(v))
    # Defensive guard: real internodes always have non-zero length; this
    # only fires under broken sim output and prevents a divide-by-zero.
    if n < 1e-12:
        return np.array([0.0, 1.0, 0.0])
    return v / n


def _angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    c = float(np.clip(np.dot(a, b), -1.0, 1.0))
    return math.degrees(math.acos(c))


def _stats(values: list[float]) -> dict:
    n = len(values)
    if n == 0:
        return {"mean": float("nan"), "stddev": float("nan"), "n": 0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(arr.mean()),
        "stddev": float(arr.std(ddof=0)),
        "n": n,
    }


# ── Insertion angles ──────────────────────────────────────────────────────

def _insertion_angle_metrics(
    internodes: list[Internode],
    axis_orders: dict[int, int],
) -> dict:
    """For each internode L:
      vs_parent      = angle(L_tangent, L.parent_node.parent_internode_tangent),
                       skipped if parent_node has no incoming internode.
      vs_main_sibling = angle(L_tangent, sibling_tangent) where sibling is the
                       unique child of L.parent_node with is_main_axis=True
                       and not L itself; skipped when no such sibling exists.
    Both grouped by axis_orders[id(L)].
    """
    by_parent: dict[int, list[float]] = defaultdict(list)
    by_main: dict[int, list[float]] = defaultdict(list)

    for L in internodes:
        order = axis_orders[id(L)]
        L_t = _tangent(L)
        node = L.parent_node

        incoming = node.parent_internode
        if incoming is not None:
            by_parent[order].append(_angle_deg(L_t, _tangent(incoming)))

        main_sib: Internode | None = None
        # Sim invariant: at most one main-axis child per node. We take the
        # first match and break; multiple main-axis siblings would indicate
        # a broken sim output (silently degraded measurement) — not asserted
        # so diagnostics never crashes on imperfect input.
        for c in node.children_internodes:
            if c is L:
                continue
            if c.is_main_axis:
                main_sib = c
                break
        if main_sib is not None:
            by_main[order].append(_angle_deg(L_t, _tangent(main_sib)))

    return {
        "insertion_angle_deg_vs_parent": {k: _stats(v) for k, v in by_parent.items()},
        "insertion_angle_deg_vs_main_sibling": {k: _stats(v) for k, v in by_main.items()},
    }


# ── Axis chains and divergence ────────────────────────────────────────────

def _walk_axis_chains(root: Node) -> list[list[Internode]]:
    """Return chains so divergence azimuths are measured along a single
    anatomical axis. Each chain = maximal sequence of internodes linked by
    is_main_axis=True continuation.
    """
    chains: list[list[Internode]] = []
    visited: set[int] = set()
    for iod in _walk_internodes(root):
        if id(iod) in visited:
            continue
        if iod.parent_node.parent_internode is not None and iod.is_main_axis:
            continue
        chain: list[Internode] = [iod]
        visited.add(id(iod))
        cur = iod
        while True:
            nxt: Internode | None = None
            for c in cur.child_node.children_internodes:
                if c.is_main_axis:
                    nxt = c
                    break
            if nxt is None:
                break
            chain.append(nxt)
            visited.add(id(nxt))
            cur = nxt
        chains.append(chain)
    return chains


def _frame_perpendicular_to(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    # why: Duplicated from sim/phyllotaxy.py. Both must agree on basis
    # convention so divergence measurements use the same in-plane basis
    # the simulator used to place lateral buds.
    canonical = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    right = canonical - np.dot(canonical, d) * d
    right = right / np.linalg.norm(right)
    up = np.cross(d, right)
    return right, up


def _divergence_angle_metrics(
    chains: list[list[Internode]],
    axis_orders: dict[int, int],
) -> dict:
    """Consecutive azimuth deltas (mod 360°) between lateral pairs along
    each axis chain, measured in the basis perpendicular to the chain
    tangent. Grouped by the LATERAL's axis_order (not the chain's).
    """
    by_order: dict[int, list[float]] = defaultdict(list)
    for chain in chains:
        laterals: list[tuple[Internode, Internode]] = []
        for cur in chain:
            for c in cur.child_node.children_internodes:
                if not c.is_main_axis:
                    laterals.append((cur, c))
        if len(laterals) < 2:
            continue

        prev_az: float | None = None
        for cur, lat in laterals:
            T = _tangent(cur)
            right, up = _frame_perpendicular_to(T)
            lat_t = _tangent(lat)
            az = math.degrees(math.atan2(
                float(np.dot(lat_t, up)),
                float(np.dot(lat_t, right)),
            ))
            if prev_az is not None:
                diff = (az - prev_az) % 360.0
                by_order[axis_orders[id(lat)]].append(diff)
            prev_az = az

    return {"divergence_angle_deg": {k: _stats(v) for k, v in by_order.items()}}


# ── Counts ────────────────────────────────────────────────────────────────

def _bud_state_histogram(nodes: list[Node]) -> dict[str, int]:
    counts: dict[str, int] = {s.name: 0 for s in BudState}
    for n in nodes:
        if n.terminal_bud is not None:
            counts[n.terminal_bud.state.name] += 1
        for b in n.lateral_buds:
            counts[b.state.name] += 1
        for b in n.dormant_reserve_buds:
            counts[b.state.name] += 1
    return counts


def _sympodial_fork_count(nodes: list[Node]) -> int:
    return sum(1 for n in nodes if n.sympodial_fork)


# ── Architecture ──────────────────────────────────────────────────────────

def _height_and_crown(nodes: list[Node]) -> tuple[float, float]:
    """Returns (tree_height, crown_radius). Crown band is y > 0.4*height
    using bent positions; matches what the rendered .glb actually looks like.
    """
    if not nodes:
        return (0.0, 0.0)
    ys = [float((n.position + n.sag_offset)[1]) for n in nodes]
    height = max(ys)
    threshold = 0.4 * height
    crown = 0.0
    for n in nodes:
        bent = n.position + n.sag_offset
        if float(bent[1]) > threshold:
            r = float(math.hypot(bent[0], bent[2]))
            if r > crown:
                crown = r
    return (height, crown)


def _trunk_base_diameter(root: Node) -> float:
    if not root.children_internodes:
        return 0.0
    return max(float(iod.diameter) for iod in root.children_internodes)


# ── Leaf area ─────────────────────────────────────────────────────────────

def _total_leaf_area(tree: Tree, cfg: "Config") -> float:
    """Sum of rendered leaf surface areas across foliage sites.

    Per site, per cluster: two quads in the renderer.
      * Quad A is parallelogram-sheared by ``splay_deg`` (axes are
        ``rot_axis_u`` and ``leaf_up`` = cos(splay)·d + sin(splay)·rot_axis_u),
        so its area is ``eff² · aspect · cos(splay_rad)``.
      * Quad B is rectangular (axes ``rot_axis_w`` and ``leaf_up`` are
        orthogonal), with area ``eff² · aspect``.
    Total per cluster = ``eff² · aspect · (1 + cos(splay_rad))``.
    """
    from palubicki.geom.leaves import _collect_foliage_sites, compute_effective_leaf_size

    g = cfg.geom
    sites = _collect_foliage_sites(tree, g.foliage_depth)
    if not sites:
        return 0.0
    splay_rad = math.radians(g.leaf_splay_deg)
    cluster_factor = g.leaf_cluster_count * g.leaf_aspect * (1.0 + math.cos(splay_rad))
    total = 0.0
    for _center, _direction, source_iod in sites:
        eff = compute_effective_leaf_size(source_iod, g.leaf_size, g.leaf_sun_shade_k)
        total += (eff * eff) * cluster_factor
    return total


# ── Public entry point ────────────────────────────────────────────────────

def compute_metrics(
    tree: "Tree | list[Tree]",
    *,
    cfg: "Config | None" = None,
) -> dict:
    """Compute structural metrics for one or many trees.

    Tree     → flat dict per the schema in docs/superpowers/specs/
                2026-05-27-tree-diagnostics-design.md.
    list[Tree] → aggregated dict (mean / stddev / per_seed at each leaf).

    `cfg` is optional; only consumed by total_leaf_area.
    """
    if isinstance(tree, list):
        # Multi-seed path lands in Task 7. Stub for now.
        raise NotImplementedError("multi-seed compute_metrics arrives in Task 7")

    nodes = _walk_nodes(tree.root)
    internodes = _walk_internodes(tree.root)
    axis_orders = _axis_orders(tree.root)
    chains = _walk_axis_chains(tree.root)

    height, crown_radius = _height_and_crown(nodes)

    out: dict = {}
    out.update(_strahler_metrics(tree.root))
    out.update(_insertion_angle_metrics(internodes, axis_orders))
    out.update(_divergence_angle_metrics(chains, axis_orders))
    out["sympodial_fork_count"] = _sympodial_fork_count(nodes)
    out["bud_state_histogram"] = _bud_state_histogram(nodes)
    out["tree_height"] = height
    out["trunk_base_diameter"] = _trunk_base_diameter(tree.root)
    out["crown_radius"] = crown_radius
    if cfg is not None:
        out["total_leaf_area"] = _total_leaf_area(tree, cfg)
    else:
        out["total_leaf_area"] = 0.0
    return out
