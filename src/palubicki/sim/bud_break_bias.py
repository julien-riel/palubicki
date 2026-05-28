"""Position-based lateral-bud-break bias along an axis (acro/basi/mesotonic)."""
from __future__ import annotations

from typing import Literal

from palubicki.sim.tree import Bud, Tree


def position_weight(
    node_index: int,
    axis_length: int,
    mode: Literal["uniform", "acrotonic", "basitonic", "mesotonic"],
    strength: float,
) -> float:
    """Position-based multiplier in [0, 1] for lateral-bud quality.

    ``node_index`` is 0 at the axis base, ``axis_length - 1`` at the tip.
    ``strength`` in [0, 1]: 0 = no bias (returns 1.0 in any mode),
    1 = full bias (disfavored end returns 0.0).
    """
    if mode == "uniform" or strength == 0.0 or axis_length <= 1:
        return 1.0

    t = node_index / (axis_length - 1)  # 0 at base, 1 at tip

    if mode == "acrotonic":
        shape = t
    elif mode == "basitonic":
        shape = 1.0 - t
    elif mode == "mesotonic":
        shape = 1.0 - 2.0 * abs(t - 0.5)  # tent function peaking at t=0.5
    else:
        raise ValueError(
            f"unknown bud_break_bias mode: {mode!r} "
            f"(expected 'uniform'|'acrotonic'|'basitonic'|'mesotonic')"
        )

    return (1.0 - strength) + strength * shape


def compute_axis_positions(tree: Tree) -> dict[Bud, tuple[int, int]]:
    """Map each lateral / dormant-reserve bud to ``(node_index, axis_length)``.

    ``axis_length`` is the number of internodes in the main-axis chain the
    bud's parent_node sits on; ``node_index`` is 0 at the chain's base
    (first internode's child_node) and ``axis_length - 1`` at the tip.

    Terminal buds are intentionally excluded — bud-break bias only modulates
    laterals.
    """
    out: dict[Bud, tuple[int, int]] = {}
    for chain in _walk_main_axis_chains(tree.root):
        L = len(chain)
        for i, iod in enumerate(chain):
            child_node = iod.child_node
            for b in child_node.lateral_buds:
                out[b] = (i, L)
            for b in child_node.dormant_reserve_buds:
                out[b] = (i, L)
    return out


def _walk_main_axis_chains(root):
    """Iterative walk: each chain is a maximal sequence of internodes linked
    by ``is_main_axis=True`` continuation. Mirrors ``diagnostics._walk_axis_chains``
    but kept local to avoid a cross-module dependency on diagnostics."""
    chains = []
    visited: set[int] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        for iod in node.children_internodes:
            stack.append(iod.child_node)
            if id(iod) in visited:
                continue
            # Start a chain at any internode that isn't a main-axis continuation
            # of a parent internode (i.e. trunk start OR lateral branch start).
            parent_iod = iod.parent_node.parent_internode
            if parent_iod is not None and iod.is_main_axis:
                continue
            chain = [iod]
            visited.add(id(iod))
            cur = iod
            while True:
                nxt = next(
                    (c for c in cur.child_node.children_internodes if c.is_main_axis),
                    None,
                )
                if nxt is None:
                    break
                chain.append(nxt)
                visited.add(id(nxt))
                cur = nxt
            chains.append(chain)
    return chains
