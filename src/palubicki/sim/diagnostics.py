from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
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

    out: dict = {}
    out.update(_strahler_metrics(tree.root))
    return out
