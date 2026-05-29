# src/palubicki/sim/sympodial.py
from __future__ import annotations

from palubicki.config import SympodialConfig
from palubicki.sim.tree import Bud, BudState, Tree


def promote_lateral_if_failing(
    tree: Tree,
    quality: dict[Bud, float],
    cfg: SympodialConfig,
) -> int:
    """Promote a lateral when its parent terminal has stagnated.

    For every active terminal_bud whose quality is below cfg.q_threshold
    for cfg.n_consecutive_steps consecutive iterations:
      - pick the sibling lateral_bud with the highest Q > 0
      - swap in parent node: the lateral becomes the new terminal_bud
        and is removed from lateral_buds; the old terminal is marked DEAD
      - the promoted lateral inherits the old terminal's axis_order
        (main-axis alignment) and its low_quality_steps counter is reset

    Returns the number of promotions performed this call.
    """
    if not cfg.enabled:
        return 0

    promotions = 0
    for bud in list(tree.active_buds):
        if bud.state is not BudState.ACTIVE:
            continue
        node = bud.parent_node
        if node.terminal_bud is not bud:
            continue

        q = quality.get(bud, 0.0)
        if q < cfg.q_threshold:
            bud.low_quality_steps += 1
        else:
            bud.low_quality_steps = 0
            continue

        if bud.low_quality_steps < cfg.n_consecutive_steps:
            continue

        candidates = [
            lat for lat in node.lateral_buds
            if lat.state is BudState.ACTIVE and quality.get(lat, 0.0) > 0.0
        ]
        if not candidates:
            continue

        best = max(candidates, key=lambda b: quality.get(b, 0.0))

        node.lateral_buds.remove(best)
        node.terminal_bud = best
        best.axis_order = bud.axis_order
        # The promoted lateral now continues the parent axis, so it inherits that
        # axis's phyllotactic ordinal (#24) — keeping divergence continuous across
        # the sympodial fork instead of restarting from the lateral's 0.
        best.axis_node_ordinal = bud.axis_node_ordinal

        bud.state = BudState.DEAD
        node.sympodial_fork = True

        best.low_quality_steps = 0

        promotions += 1

    tree.active_buds = [b for b in tree.active_buds if b.state is not BudState.DEAD]
    return promotions
