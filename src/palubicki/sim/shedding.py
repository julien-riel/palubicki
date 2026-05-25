# src/palubicki/sim/shedding.py
from __future__ import annotations

from palubicki.config import SheddingConfig
from palubicki.sim.tree import Bud, BudState, Node, Tree


def record_qualities(tree: Tree, *, quality: dict[Bud, int]) -> None:
    """Push subtree quality (sum of bud Q in subtree) onto each internode's history."""
    _push(tree.root, quality)


def _push(root: Node, quality: dict[Bud, int]) -> int:
    """Iterative post-order: compute subtree quality and push onto parent internode."""
    # Build post-order traversal (children before parents)
    order: list[Node] = []
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        order.append(node)
        for iod in node.children_internodes:
            stack.append(iod.child_node)
    # order is reverse-DFS (pre-order reversed = post-order)
    subtree_q: dict[int, int] = {}
    for node in reversed(order):
        total = 0
        for bud in _node_buds(node):
            total += quality.get(bud, 0)
        for iod in node.children_internodes:
            total += subtree_q.get(id(iod.child_node), 0)
        subtree_q[id(node)] = total
        if node.parent_internode is not None:
            node.parent_internode.push_quality(float(total))
    return subtree_q.get(id(root), 0)


def shed_low_quality(tree: Tree, *, cfg: SheddingConfig) -> None:
    if not cfg.enabled:
        return
    # Walk root-down; if an internode's average quality is below threshold AND its history is full,
    # remove its subtree.
    _walk_and_shed(tree.root, tree, cfg)


def _walk_and_shed(root: Node, tree: Tree, cfg: SheddingConfig) -> None:
    """Iterative pre-order walk: shed low-quality subtrees."""
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        # iterate over a copy: we may mutate children_internodes
        for iod in list(node.children_internodes):
            if len(iod.quality_history) >= cfg.window and iod.average_quality() < cfg.quality_threshold:
                _kill_subtree(iod.child_node, tree)
                # Identity-based filtering (faster than list.remove and unaffected
                # by any future __eq__ behavior on Internode/Node).
                node.children_internodes = [i for i in node.children_internodes if i is not iod]
                tree.all_internodes = [i for i in tree.all_internodes if i is not iod]
            else:
                stack.append(iod.child_node)


def _kill_subtree(root: Node, tree: Tree) -> None:
    """Iterative DFS: mark all buds DEAD and remove descendant internodes."""
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        for bud in _node_buds(node):
            bud.state = BudState.DEAD
            tree.active_buds[:] = [b for b in tree.active_buds if b is not bud]
        for iod in node.children_internodes:
            stack.append(iod.child_node)
            tree.all_internodes[:] = [i for i in tree.all_internodes if i is not iod]


def _node_buds(node: Node) -> list[Bud]:
    res: list[Bud] = []
    if node.terminal_bud is not None:
        res.append(node.terminal_bud)
    res.extend(node.lateral_buds)
    return res
