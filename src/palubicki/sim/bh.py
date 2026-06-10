from __future__ import annotations

from palubicki.sim.tree import Bud, Node, Tree


def allocate(
    tree: Tree,
    *,
    quality: dict[Bud, int],
    alpha: float,
    lambda_apical: float,
    v_subtree: dict[int, float] | None = None,
    v_total_override: float | None = None,
) -> dict[Bud, float]:
    """Borchert-Honda two-pass allocation. Returns the continuous flux v_b per bud.

    If ``v_subtree`` is provided (precomputed by ``compute_v_subtree``), the basipetal
    pass is skipped — useful when the caller also feeds shedding from the same dict.

    ``v_total_override`` (#L1 carbon spike): when given, it REPLACES the abstract
    ``alpha · Σ quality`` resource total — e.g. a carbon magnitude funded by the lit
    leaf area the canopy actually captures. Only the TOTAL changes; the acropetal
    distribution still splits by the topological ``quality`` / ``v_subtree`` shares,
    so the shedding currency (``v_subtree``) is untouched. ``None`` ⇒ legacy total.
    """
    if v_subtree is None:
        v_subtree = compute_v_subtree(tree, quality)
    v_total = (
        v_total_override if v_total_override is not None
        else alpha * v_subtree[id(tree.root)]
    )

    # Acropetal pass: distribute v_total downward
    v_by_bud: dict[Bud, float] = dict.fromkeys(tree.active_buds, 0.0)
    _distribute(tree.root, v_total, quality, v_subtree, lambda_apical, v_by_bud)
    return v_by_bud


def compute_v_subtree(tree: Tree, quality: dict[Bud, int]) -> dict[int, float]:
    """Basipetal sum of bud quality per subtree, keyed by ``id(node)``."""
    out: dict[int, float] = {}
    _compute_v_subtree(tree.root, quality, out)
    return out


def _compute_v_subtree(root: Node, quality: dict[Bud, int], out: dict[int, float]) -> float:
    """Iterative post-order: compute v_subtree for each node."""
    # Build traversal order (pre-order), then process in reverse (post-order)
    order: list[Node] = []
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        order.append(node)
        for iod in node.children_internodes:
            stack.append(iod.child_node)
    # Process in post-order (children before parents)
    for node in reversed(order):
        total = sum(out[id(iod.child_node)] for iod in node.children_internodes)
        for bud in _node_buds(node):
            total += quality.get(bud, 0)
        out[id(node)] = total
    return out.get(id(root), 0.0)


def _distribute(
    root: Node,
    v_root: float,
    quality: dict[Bud, int],
    v_subtree: dict[int, float],
    lam: float,
    v_by_bud: dict[Bud, float],
) -> None:
    """Iterative pre-order: distribute resource v_here to each node's buds/children."""
    # Stack carries (node, v_here) pairs
    stack: list[tuple[Node, float]] = [(root, v_root)]
    while stack:
        node, v_here = stack.pop()

        if v_here <= 0:
            continue

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
                continue
            # Apply BH formula between terminal (main) and lateral buds
            denom = lam * q_m + (1.0 - lam) * q_l
            if denom <= 0:
                # all quality in one group — give it all proportionally
                for b in buds:
                    qb = quality.get(b, 0)
                    v_by_bud[b] = v_here * qb / total_q
                continue
            v_terminal = v_here * (lam * q_m) / denom if terminal else 0.0
            v_lateral = v_here - v_terminal
            if terminal:
                v_by_bud[terminal] = v_terminal
            if laterals:
                lat_q_total = q_l
                for b in laterals:
                    qb = quality.get(b, 0)
                    share = qb / lat_q_total if lat_q_total > 0 else 0.0
                    v_by_bud[b] = v_lateral * share
            continue

        # Otherwise: split between main axis (child + maybe terminal_bud) and laterals
        # (lateral_children internodes + node.lateral_buds at this node).
        main_child = next((iod for iod in children if iod.is_main_axis), None)
        lateral_children = [iod for iod in children if not iod.is_main_axis]

        q_main = v_subtree.get(id(main_child.child_node), 0.0) if main_child else 0.0
        # Include terminal bud at this node if it hasn't grown yet (rare since
        # the terminal bud typically becomes the main_child).
        terminal_here = node.terminal_bud if main_child is None else None
        if terminal_here is not None:
            q_main += quality.get(terminal_here, 0)

        q_lat = sum(v_subtree.get(id(iod.child_node), 0.0) for iod in lateral_children)
        # Include node.lateral_buds at this node: these are NEW laterals that have
        # not yet grown into internodes. Without them, laterals starve forever.
        laterals_here = list(node.lateral_buds)
        q_lat += sum(quality.get(b, 0) for b in laterals_here)

        denom = lam * q_main + (1.0 - lam) * q_lat
        if denom <= 0:
            continue
        v_main = v_here * (lam * q_main) / denom
        v_lat = v_here - v_main

        if main_child:
            stack.append((main_child.child_node, v_main))
        elif terminal_here is not None and q_main > 0:
            v_by_bud[terminal_here] = v_main

        if q_lat > 0:
            for iod in lateral_children:
                share = v_subtree.get(id(iod.child_node), 0.0) / q_lat
                stack.append((iod.child_node, v_lat * share))
            for b in laterals_here:
                qb = quality.get(b, 0)
                share = qb / q_lat
                v_by_bud[b] = v_lat * share


def _node_buds(node: Node) -> list[Bud]:
    res: list[Bud] = []
    if node.terminal_bud is not None:
        res.append(node.terminal_bud)
    res.extend(node.lateral_buds)
    return res
