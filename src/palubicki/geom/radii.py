from __future__ import annotations

from palubicki.sim.tree import Internode, Node, Tree


def compute_radii(tree: Tree, *, r_tip: float, exponent: float) -> None:
    """Fill `internode.diameter` in-place using pipe model r^n = sum(r_child^n).

    Each internode's radius is determined by its child subtree:
    - tip (no descendant internodes): r_tip
    - otherwise: r = (Σ r_child^n)^(1/n) over the child node's outgoing internodes
    """
    for iod in tree.root.children_internodes:
        _set_radius(iod.child_node, iod, r_tip, exponent)


def _set_radius(node: Node, incoming_iod: Internode, r_tip: float, n: float) -> float:
    if not node.children_internodes:
        r = r_tip
    else:
        sum_pow = 0.0
        for child_iod in node.children_internodes:
            r_child = _set_radius(child_iod.child_node, child_iod, r_tip, n)
            sum_pow += r_child**n
        r = sum_pow ** (1.0 / n)
    incoming_iod.diameter = 2.0 * r
    return r
