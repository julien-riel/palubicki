# src/palubicki/sim/shedding.py
from __future__ import annotations

from palubicki.config import SheddingConfig
from palubicki.sim.bh import compute_v_subtree
from palubicki.sim.reiteration import activate_reserves_on_shed
from palubicki.sim.tree import Bud, BudState, Node, Tree


def record_qualities(
    tree: Tree,
    *,
    quality: dict[Bud, int] | None = None,
    v_subtree: dict[int, float] | None = None,
) -> None:
    """Push subtree quality (sum of bud Q in subtree) onto each internode's history.

    Pass either ``quality`` (will compute subtree quality internally) or ``v_subtree``
    (precomputed by ``bh.compute_v_subtree``) — the latter avoids a redundant traversal
    when ``allocate`` already produced it.
    """
    if v_subtree is None:
        if quality is None:
            raise ValueError("record_qualities requires either quality or v_subtree")
        v_subtree = compute_v_subtree(tree, quality)
    for iod in tree.all_internodes:
        iod.push_quality(float(v_subtree.get(id(iod.child_node), 0.0)))


def shed_low_quality(tree: Tree, *, cfg: SheddingConfig) -> None:
    if not cfg.enabled:
        return
    dead_bud_ids: set[int] = set()
    dead_iod_ids: set[int] = set()
    activated_buds: list[Bud] = []
    _walk_and_shed(tree.root, cfg, dead_bud_ids, dead_iod_ids, activated_buds)
    if dead_bud_ids:
        tree.active_buds = [b for b in tree.active_buds if id(b) not in dead_bud_ids]
    if dead_iod_ids:
        tree.all_internodes = [i for i in tree.all_internodes if id(i) not in dead_iod_ids]
    if activated_buds:
        tree.active_buds.extend(activated_buds)


def _walk_and_shed(
    root: Node,
    cfg: SheddingConfig,
    dead_bud_ids: set[int],
    dead_iod_ids: set[int],
    activated_buds: list[Bud],
) -> None:
    """Iterative pre-order walk: shed low-quality subtrees, activate reserves."""
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        for iod in list(node.children_internodes):
            if (
                len(iod.quality_history) >= cfg.window
                and iod.average_quality() < cfg.quality_threshold
            ):
                _kill_subtree(iod.child_node, dead_bud_ids, dead_iod_ids)
                node.children_internodes = [
                    i for i in node.children_internodes if i is not iod
                ]
                dead_iod_ids.add(id(iod))
                # Phase 2B: wake up reserves on the parent of the shed branch.
                activated = activate_reserves_on_shed(
                    node, n_to_activate=cfg.reactivation_count
                )
                activated_buds.extend(activated)
            else:
                stack.append(iod.child_node)


def _kill_subtree(root: Node, dead_bud_ids: set[int], dead_iod_ids: set[int]) -> None:
    """Iterative DFS: mark all buds DEAD, collect identities of buds and internodes to remove."""
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        for bud in _node_buds(node):
            bud.state = BudState.DEAD
            dead_bud_ids.add(id(bud))
        for iod in node.children_internodes:
            stack.append(iod.child_node)
            dead_iod_ids.add(id(iod))


def _node_buds(node: Node) -> list[Bud]:
    res: list[Bud] = []
    if node.terminal_bud is not None:
        res.append(node.terminal_bud)
    res.extend(node.lateral_buds)
    return res
