# src/palubicki/sim/reiteration.py
from __future__ import annotations

from palubicki.sim.tree import Bud, BudState, Node


def activate_reserves_on_shed(
    parent_node: Node,
    n_to_activate: int = 1,
) -> list[Bud]:
    """Activate up to ``n_to_activate`` RESERVE buds attached to ``parent_node``.

    Activated buds transition RESERVE → ACTIVE, are moved from
    ``dormant_reserve_buds`` to ``lateral_buds``, and have their counters
    (low_quality_steps, low_light_steps, age) reset to 0.

    If fewer reserves exist than requested, activates all available. If
    n_to_activate <= 0 or no reserves remain, returns [].

    The caller is responsible for appending returned buds to
    ``tree.active_buds``.
    """
    if n_to_activate <= 0 or not parent_node.dormant_reserve_buds:
        return []
    n_actual = min(n_to_activate, len(parent_node.dormant_reserve_buds))
    activated: list[Bud] = []
    for _ in range(n_actual):
        bud = parent_node.dormant_reserve_buds.pop()
        bud.state = BudState.ACTIVE
        bud.low_quality_steps = 0
        bud.low_light_steps = 0
        bud.age = 0
        parent_node.lateral_buds.append(bud)
        activated.append(bud)
    return activated
