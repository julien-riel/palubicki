# src/palubicki/sim/shade_mortality.py
from __future__ import annotations

from palubicki.config import ShadeMortalityConfig
from palubicki.sim.tree import Bud, BudState


def kill_shaded_buds(
    buds: list[Bud],
    light_factor: dict[Bud, float],
    cfg: ShadeMortalityConfig,
) -> int:
    """Mark living buds DEAD when light_factor stays below threshold for N steps.

    Returns the number of buds killed in this call.

    Both ACTIVE and DORMANT buds are considered: a DORMANT bud is living tissue
    that is merely below the vigor gate this iteration (it stays in ``active_buds``
    and is re-evaluated every step), so a perpetually-shaded dormant bud must accrue
    mortality rather than persist forever. The shade counter resets whenever the bud
    is well-lit, so a dormant bud that recovers light keeps its second chance.
    RESERVE / DEAD are skipped entirely (their counters are not touched).

    A bud missing from ``light_factor`` is treated as receiving full sun (1.0)
    — a conservative default that does not trigger mortality.
    """
    if not cfg.enabled:
        return 0
    killed = 0
    for bud in buds:
        if bud.state in (BudState.RESERVE, BudState.DEAD):
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
