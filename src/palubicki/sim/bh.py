from __future__ import annotations

import math

from palubicki.sim.tree import Bud, Internode, Node, Tree


def allocate(
    tree: Tree,
    *,
    quality: dict[Bud, int],
    alpha: float,
    lambda_apical: float,
) -> dict[Bud, int]:
    """Borchert-Honda two-pass allocation. Returns floor(v_b) per bud."""
    # Basipetal pass: v_subtree per node id = sum(v_subtree per child) + sum(Q per bud at this node)
    # Use id(node) as key because Node is a mutable dataclass (unhashable).
    v_subtree: dict[int, float] = {}
    _compute_v_subtree(tree.root, quality, v_subtree)
    v_total = alpha * v_subtree[id(tree.root)]

    # Acropetal pass: distribute v_total downward
    n_by_bud: dict[Bud, int] = {b: 0 for b in tree.active_buds}
    _distribute(tree.root, v_total, quality, v_subtree, lambda_apical, n_by_bud)
    return n_by_bud


def _compute_v_subtree(node: Node, quality: dict[Bud, int], out: dict[int, float]) -> float:
    total = 0.0
    for iod in node.children_internodes:
        total += _compute_v_subtree(iod.child_node, quality, out)
    for bud in _node_buds(node):
        total += quality.get(bud, 0)
    out[id(node)] = total
    return total


def _distribute(
    node: Node,
    v_here: float,
    quality: dict[Bud, int],
    v_subtree: dict[int, float],
    lam: float,
    n_by_bud: dict[Bud, int],
) -> None:
    if v_here <= 0:
        return

    buds = _node_buds(node)
    children = node.children_internodes

    # If this node has only buds (a tip), split using BH formula between terminal and lateral buds.
    # Terminal bud acts as main axis; lateral buds collectively act as lateral axis.
    if not children:
        terminal = node.terminal_bud
        laterals = list(node.lateral_buds)
        q_m = quality.get(terminal, 0) if terminal else 0
        q_l = sum(quality.get(b, 0) for b in laterals)
        total_q = q_m + q_l
        if total_q == 0:
            return
        # Apply BH formula between terminal (main) and lateral buds
        denom = lam * q_m + (1.0 - lam) * q_l
        if denom <= 0:
            # all quality in one group — give it all proportionally
            for b in buds:
                qb = quality.get(b, 0)
                n_by_bud[b] = math.floor(v_here * qb / total_q)
            return
        v_terminal = v_here * (lam * q_m) / denom if terminal else 0.0
        v_lateral = v_here - v_terminal
        if terminal:
            n_by_bud[terminal] = math.floor(v_terminal)
        if laterals:
            lat_q_total = q_l
            for b in laterals:
                qb = quality.get(b, 0)
                share = qb / lat_q_total if lat_q_total > 0 else 0.0
                n_by_bud[b] = math.floor(v_lateral * share)
        return

    # Otherwise: split between main axis child and lateral(s)
    main_child = next((iod for iod in children if iod.is_main_axis), None)
    lateral_children = [iod for iod in children if not iod.is_main_axis]

    q_main = v_subtree.get(id(main_child.child_node), 0.0) if main_child else 0.0
    q_lat = sum(v_subtree.get(id(iod.child_node), 0.0) for iod in lateral_children)

    denom = lam * q_main + (1.0 - lam) * q_lat
    if denom <= 0:
        return
    v_main = v_here * (lam * q_main) / denom
    v_lat = v_here - v_main

    if main_child:
        _distribute(main_child.child_node, v_main, quality, v_subtree, lam, n_by_bud)
    if lateral_children and q_lat > 0:
        for iod in lateral_children:
            share = v_subtree.get(id(iod.child_node), 0.0) / q_lat
            _distribute(iod.child_node, v_lat * share, quality, v_subtree, lam, n_by_bud)


def _node_buds(node: Node) -> list[Bud]:
    res: list[Bud] = []
    if node.terminal_bud is not None:
        res.append(node.terminal_bud)
    res.extend(node.lateral_buds)
    return res
