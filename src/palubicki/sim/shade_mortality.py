# src/palubicki/sim/shade_mortality.py
from __future__ import annotations

from palubicki.config import ShadeMortalityConfig
from palubicki.sim.tree import Bud, BudState


def kill_shaded_buds(
    buds: list[Bud],
    light_factor: dict[Bud, float],
    cfg: ShadeMortalityConfig,
) -> int:
    """Mark ACTIVE buds DEAD when light_factor stays below threshold for N steps.

    Returns the number of buds killed in this call.

    Only ACTIVE buds are considered. RESERVE / DORMANT / DEAD are skipped
    entirely (their counters are not touched).

    A bud missing from ``light_factor`` is treated as receiving full sun (1.0)
    — a conservative default that does not trigger mortality.
    """
    if not cfg.enabled:
        return 0
    killed = 0
    for bud in buds:
        if bud.state is not BudState.ACTIVE:
            continue
        lf = light_factor.get(bud, 1.0)
        if lf < cfg.light_threshold:
            bud.low_light_steps += 1
            if bud.low_light_steps >= cfg.n_consecutive_steps:
                bud.state = BudState.DEAD
                killed += 1
        else:
            bud.low_light_steps = 0
    return killed
