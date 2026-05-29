from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass
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

def _total_leaf_area(tree: Tree, cfg: Config) -> float:
    """Sum of rendered leaf surface areas across foliage sites.

    Each foliage site emits ``cluster_count`` pairs of perpendicular blades.
    For each pair:
      * Plane A: basis_u = rot_axis_u, basis_v = leaf_up.  Because
        ``leaf_up = cos(splay)·d + sin(splay)·rot_axis_u``, the area of the
        lifted blade is ``unit_blade_area * cos(splay_rad)``.
      * Plane B: basis_u = rot_axis_w, basis_v = leaf_up.  rot_axis_w is
        perpendicular to leaf_up, so the area equals ``unit_blade_area * 1.0``.

    The unit blade area is computed once from ``build_blade(length=1, width=aspect, …)``
    and then scaled by eff_size² per site.
    """
    from palubicki.geom.leaf_blade import build_blade
    from palubicki.geom.leaves import _collect_foliage_sites, compute_effective_leaf_size

    g = cfg.geom
    sites = _collect_foliage_sites(tree, g.foliage_depth)
    if not sites:
        return 0.0

    # Build unit-blade template once to get its 2D area.
    blade_pos, _, _, blade_idx = build_blade(
        length=1.0, width=g.leaf_aspect, shape=g.leaf_shape,
        margin=g.leaf_margin, margin_depth=g.leaf_margin_depth,
        margin_count=g.leaf_margin_count,
    )
    pos2d = blade_pos.astype(np.float64)
    tris = blade_idx.reshape(-1, 3)
    e1 = pos2d[tris[:, 1]] - pos2d[tris[:, 0]]
    e2 = pos2d[tris[:, 2]] - pos2d[tris[:, 0]]
    unit_blade_area = float(0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum())

    splay_rad = math.radians(g.leaf_splay_deg)
    # n_planes mirrors the logic in build_leaves_primitive: cross-blade only
    # for linear (needle) shapes; single plane for all parametric shapes.
    n_planes = 2 if g.leaf_shape == "linear" else 1
    # Plane A area is reduced by cos(splay_rad) due to the shear from splay.
    # Plane B area is unchanged (basis_u⊥leaf_up always), but only present
    # when n_planes == 2.
    plane_a_factor = math.cos(splay_rad)
    plane_b_factor = 1.0 if n_planes == 2 else 0.0
    pair_area = unit_blade_area * (plane_a_factor + plane_b_factor)

    total = 0.0
    for _center, _direction, source_iod in sites:
        eff = compute_effective_leaf_size(source_iod, g.leaf_size, g.leaf_sun_shade_k)
        total += g.leaf_cluster_count * pair_area * (eff * eff)
    return total


# ── Public entry point ────────────────────────────────────────────────────

def compute_metrics(
    tree: Tree | list[Tree],
    *,
    cfg: Config | None = None,
) -> dict:
    """Compute structural metrics for one or many trees.

    Tree     → flat dict per the schema in docs/superpowers/specs/
                2026-05-27-tree-diagnostics-design.md.
    list[Tree] → aggregated dict (mean / stddev / per_seed at each leaf).

    `cfg` is optional; only consumed by total_leaf_area.
    """
    if isinstance(tree, list):
        per_tree = [compute_metrics(t, cfg=cfg) for t in tree]
        return _aggregate(per_tree)

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


# ── Multi-seed aggregation ────────────────────────────────────────────────

_SCALAR_KEYS = (
    "strahler_order_max",
    "horton_bifurcation_ratio_mean",
    "sympodial_fork_count",
    "tree_height",
    "trunk_base_diameter",
    "crown_radius",
    "total_leaf_area",
)

_HISTOGRAM_KEYS = (
    "strahler_order_histogram",
    "bud_state_histogram",
)

_ANGLE_KEYS = (
    "insertion_angle_deg_vs_parent",
    "insertion_angle_deg_vs_main_sibling",
    "divergence_angle_deg",
)


def _agg_scalar(values: list) -> dict:
    """Aggregate a list of scalars where None or NaN counts as missing."""
    non_null = [
        v for v in values
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    ]
    if not non_null:
        return {"mean": float("nan"), "stddev": float("nan"), "per_seed": values}
    arr = np.asarray(non_null, dtype=np.float64)
    return {
        "mean": float(arr.mean()),
        "stddev": float(arr.std(ddof=0)),
        "per_seed": values,
    }


def _aggregate(per_tree: list[dict]) -> dict:
    """Combine N per-tree metric dicts into a multi-seed dict.

    Scalar leaves wrap into {mean, stddev, per_seed}. Histograms union over
    bin keys (missing = 0). Per-order angle stats union over orders (missing
    = None in per_seed; excluded from mean/stddev). Per-order Horton ratios
    union over orders (missing = None).
    """
    if not per_tree:
        return {}

    out: dict = {}

    for k in _SCALAR_KEYS:
        out[k] = _agg_scalar([m[k] for m in per_tree])

    for k in _HISTOGRAM_KEYS:
        all_keys: set = set()
        for m in per_tree:
            all_keys.update(m[k].keys())
        out[k] = {
            kk: _agg_scalar([m[k].get(kk, 0) for m in per_tree])
            for kk in sorted(all_keys, key=lambda x: (isinstance(x, str), x))
        }

    all_ratio_orders: set = set()
    for m in per_tree:
        all_ratio_orders.update(m["horton_bifurcation_ratio"].keys())
    out["horton_bifurcation_ratio"] = {
        kk: _agg_scalar([m["horton_bifurcation_ratio"].get(kk) for m in per_tree])
        for kk in sorted(all_ratio_orders)
    }

    for k in _ANGLE_KEYS:
        all_orders: set = set()
        for m in per_tree:
            all_orders.update(m[k].keys())
        out[k] = {}
        for order in sorted(all_orders):
            means = [
                (m[k][order]["mean"] if order in m[k] else None)
                for m in per_tree
            ]
            out[k][order] = _agg_scalar(means)

    return out


# ── Reference-range flags and pretty-printer ──────────────────────────────

@dataclass
class MetricRanges:
    """Literature-range bounds for ✓/✗ flagging.

    Field names use a path-style convention so format_report can resolve
    the relevant value in the metrics dict:
      "horton_bifurcation_ratio_mean"             → metrics["horton_bifurcation_ratio_mean"]
      "divergence_angle_deg__orderN_mean"         → metrics["divergence_angle_deg"][N]["mean"]
      "insertion_angle_deg_vs_parent__orderN_mean" → metrics["insertion_angle_deg_vs_parent"][N]["mean"]
    A field absent from this class means no flag is rendered for that path.
    """
    horton_bifurcation_ratio_mean: tuple[float, float] = (3.0, 5.0)
    divergence_angle_deg__order1_mean: tuple[float, float] = (130.0, 145.0)
    insertion_angle_deg_vs_parent__order1_mean: tuple[float, float] = (30.0, 65.0)


DEFAULT_RANGES = MetricRanges()


def _flag(value: float | None, bounds: tuple[float, float] | None) -> str:
    if value is None or bounds is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return "—"
    lo, hi = bounds
    return "✓" if lo <= value <= hi else "✗"


def _is_multi(metrics: dict) -> bool:
    """Heuristic: in multi-seed shape, scalar leaves are dicts with per_seed."""
    v = metrics.get("tree_height")
    return isinstance(v, dict) and "per_seed" in v


def _scalar_value(metrics: dict, key: str) -> float | None:
    v = metrics.get(key)
    if v is None:
        return None
    if isinstance(v, dict) and "mean" in v:
        return v["mean"]
    return v


def _bounds_for(ranges: MetricRanges, field_name: str) -> tuple[float, float] | None:
    return getattr(ranges, field_name, None)


def _fmt_scalar(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and math.isnan(v):
        return "—"
    if isinstance(v, dict):
        mean = v["mean"]
        stddev = v["stddev"]
        mean_s = "—" if (isinstance(mean, float) and math.isnan(mean)) else f"{mean:.3g}"
        std_s = "—" if (isinstance(stddev, float) and math.isnan(stddev)) else f"{stddev:.3g}"
        return f"mean={mean_s} stddev={std_s}"
    if isinstance(v, float):
        return f"{v:.3g}"
    return str(v)


def format_report(
    metrics: dict,
    *,
    ranges: MetricRanges = DEFAULT_RANGES,
    seeds: list[int] | None = None,
    species: str | None = None,
) -> str:
    multi = _is_multi(metrics)
    lines: list[str] = []
    header = "palubicki diagnose"
    if species is not None:
        header += f" — species: {species}"
    if seeds is not None:
        if len(seeds) == 1:
            header += f", seed: {seeds[0]}"
        else:
            header += f", seeds: [{','.join(str(s) for s in seeds)}]"
    lines.append(header)
    lines.append("=" * 72)
    lines.append("")

    lines.append("Architecture")
    for k in ("tree_height", "trunk_base_diameter", "crown_radius", "total_leaf_area"):
        val = metrics.get(k)
        flag = _flag(_scalar_value(metrics, k), _bounds_for(ranges, k))
        lines.append(f"  {k:24s} {_fmt_scalar(val):28s} {flag}".rstrip())
    lines.append("")

    lines.append("Strahler / Horton")
    lines.append(f"  order_max                {_fmt_scalar(metrics.get('strahler_order_max'))}")
    if not multi:
        hist = metrics.get("strahler_order_histogram") or {}
        lines.append(f"  histogram                {dict(sorted(hist.items()))}")
        ratios = metrics.get("horton_bifurcation_ratio") or {}
        if ratios:
            ratio_strs = "   ".join(f"{n}→{n+1}: {r:.3g}" for n, r in sorted(ratios.items()))
            lines.append(f"  bifurcation_ratio        {ratio_strs}")
    bif_flag = _flag(
        _scalar_value(metrics, "horton_bifurcation_ratio_mean"),
        _bounds_for(ranges, "horton_bifurcation_ratio_mean"),
    )
    lines.append(
        f"  bif_ratio_mean           "
        f"{_fmt_scalar(metrics.get('horton_bifurcation_ratio_mean'))}  {bif_flag}".rstrip()
    )
    lines.append("")

    lines.append("Angles (observed, by child axis_order)")
    angle_blocks = [
        ("insertion (vs parent)",      "insertion_angle_deg_vs_parent",      "insertion_angle_deg_vs_parent"),
        ("insertion (vs main sib)",    "insertion_angle_deg_vs_main_sibling", None),
        ("divergence",                  "divergence_angle_deg",                "divergence_angle_deg"),
    ]
    for label, key, range_prefix in angle_blocks:
        d = metrics.get(key) or {}
        if not d:
            continue
        lines.append(f"  {label}")
        for order in sorted(d.keys()):
            stats = d[order]
            flag = ""
            if range_prefix is not None:
                bound_field = f"{range_prefix}__order{order}_mean"
                mean = stats.get("mean") if isinstance(stats, dict) else None
                flag = _flag(mean, _bounds_for(ranges, bound_field))
            lines.append(f"    order {order}                 {_fmt_scalar(stats)}  {flag}".rstrip())
    lines.append("")

    lines.append("Counts")
    lines.append(f"  sympodial_forks          {_fmt_scalar(metrics.get('sympodial_fork_count'))}")
    bh = metrics.get("bud_state_histogram") or {}
    if bh:
        if multi:
            for name in ("ACTIVE", "DORMANT", "DEAD", "RESERVE"):
                if name in bh:
                    lines.append(f"  buds.{name:10s}        {_fmt_scalar(bh[name])}")
        else:
            parts = "   ".join(f"{k}: {v}" for k, v in bh.items())
            lines.append(f"  buds                     {parts}")
    return "\n".join(lines)
