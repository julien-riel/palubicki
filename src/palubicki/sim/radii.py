from __future__ import annotations

from palubicki.sim.tree import Internode, Node, Tree


def compute_radii(tree: Tree, *, r_tip: float, exponent: float) -> None:
    """Fill `internode.diameter` in-place using pipe model r^n = sum(r_child^n).

    Each internode's radius is determined by its child subtree:
    - tip (no descendant internodes): r_tip
    - otherwise: r = (Σ r_child^n)^(1/n) over the child node's outgoing internodes
    """
    for iod in tree.root.children_internodes:
        _set_radius_iterative(iod.child_node, iod, r_tip, exponent)


def _set_radius_iterative(root_node: Node, root_iod: Internode, r_tip: float, n: float) -> None:
    """Iterative post-order computation of radii using pipe model."""
    order: list[tuple[Node, Internode]] = []
    stack: list[tuple[Node, Internode]] = [(root_node, root_iod)]
    while stack:
        node, iod = stack.pop()
        order.append((node, iod))
        for child_iod in node.children_internodes:
            stack.append((child_iod.child_node, child_iod))
    radius: dict[int, float] = {}
    for node, iod in reversed(order):
        if not node.children_internodes:
            r = r_tip
        else:
            sum_pow = sum(radius[id(child_iod.child_node)] ** n for child_iod in node.children_internodes)
            r = sum_pow ** (1.0 / n)
        iod.diameter = 2.0 * r
        radius[id(node)] = r
