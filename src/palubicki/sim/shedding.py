# src/palubicki/sim/shedding.py
from __future__ import annotations

from palubicki.config import SheddingConfig
from palubicki.sim.tree import Bud, BudState, Node, Tree


def record_qualities(tree: Tree, *, quality: dict[Bud, int]) -> None:
    """Push subtree quality (sum of bud Q in subtree) onto each internode's history."""
    _push(tree.root, quality)


def _push(node: Node, quality: dict[Bud, int]) -> int:
    subtree_q = 0
    for bud in _node_buds(node):
        subtree_q += quality.get(bud, 0)
    for iod in node.children_internodes:
        subtree_q += _push(iod.child_node, quality)
    if node.parent_internode is not None:
        node.parent_internode.push_quality(float(subtree_q))
    return subtree_q


def shed_low_quality(tree: Tree, *, cfg: SheddingConfig) -> None:
    if not cfg.enabled:
        return
    # Walk root-down; if an internode's average quality is below threshold AND its history is full,
    # remove its subtree.
    _walk_and_shed(tree.root, tree, cfg)


def _walk_and_shed(node: Node, tree: Tree, cfg: SheddingConfig) -> None:
    # iterate over a copy: we may mutate children_internodes
    for iod in list(node.children_internodes):
        if len(iod.quality_history) >= cfg.window and iod.average_quality() < cfg.quality_threshold:
            _kill_subtree(iod.child_node, tree)
            node.children_internodes.remove(iod)
            tree.all_internodes[:] = [i for i in tree.all_internodes if i is not iod]
        else:
            _walk_and_shed(iod.child_node, tree, cfg)


def _kill_subtree(node: Node, tree: Tree) -> None:
    for bud in _node_buds(node):
        bud.state = BudState.DEAD
        tree.active_buds[:] = [b for b in tree.active_buds if b is not bud]
    for iod in node.children_internodes:
        _kill_subtree(iod.child_node, tree)
        tree.all_internodes[:] = [i for i in tree.all_internodes if i is not iod]


def _node_buds(node: Node) -> list[Bud]:
    res: list[Bud] = []
    if node.terminal_bud is not None:
        res.append(node.terminal_bud)
    res.extend(node.lateral_buds)
    return res
