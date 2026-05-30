from __future__ import annotations

import math

from palubicki.sim.tree import Internode, Node, Tree


def update_diameters_incremental(
    tree: Tree, r_tip: float, exponent: float,
    vigor_ref: float = 1.0, vigor_diameter_gain: float = 0.0,
) -> None:
    """Recompute pipe-model diameters for all internodes in-place.

    Idempotent: calling multiple times on an unchanged tree yields identical
    diameters. Intended for per-iteration calls inside the simulator loop.
    Positional arguments match the existing ``compute_radii`` style so callers
    can use either form.
    """
    compute_radii(tree, r_tip=r_tip, exponent=exponent,
                  vigor_ref=vigor_ref, vigor_diameter_gain=vigor_diameter_gain)


def compute_radii(
    tree: Tree, *, r_tip: float, exponent: float,
    vigor_ref: float = 1.0, vigor_diameter_gain: float = 0.0,
) -> None:
    """Fill `internode.diameter` in-place using pipe model r^n = sum(r_child^n).

    Tip internodes (no descendant internodes) seed their radius as
    ``r_tip * (1 + vigor_diameter_gain * (1 - exp(-iod.vigor / vigor_ref)))`` so
    vigorous lineages seed thicker pipes (#20). The saturating factor bounds the
    multiplier to ``[1, 1 + vigor_diameter_gain]`` — the BH flux is heavy-tailed
    (a few tips carry flux in the hundreds), and an unbounded linear coupling let
    those outliers explode the summed trunk; saturation keeps it well-behaved.
    vigor_diameter_gain=0 -> flat r_tip (pure pipe model).
    """
    for iod in tree.root.children_internodes:
        _set_radius_iterative(iod.child_node, iod, r_tip, exponent, vigor_ref, vigor_diameter_gain)


def _set_radius_iterative(
    root_node: Node, root_iod: Internode, r_tip: float, n: float,
    vigor_ref: float, vigor_diameter_gain: float,
) -> None:
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
            sat = 1.0 - math.exp(-iod.vigor / vigor_ref) if vigor_ref > 0 else 1.0
            r = r_tip * (1.0 + vigor_diameter_gain * sat)
        else:
            sum_pow = sum(radius[id(child_iod.child_node)] ** n for child_iod in node.children_internodes)
            r = sum_pow ** (1.0 / n)
        iod.diameter = 2.0 * r
        radius[id(node)] = r
