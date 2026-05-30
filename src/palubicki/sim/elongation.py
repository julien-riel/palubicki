"""Progressive internode elongation (S-curve).

Spec: docs/superpowers/specs/2026-05-27-phase2d-temporal-dynamics-design.md (§4.3)

Design compromise: Node.position is fixed at creation to the final geometric
location (cur.position + d * length_target). The internode's effective length
ramps from 0 toward length_target via a sigmoid. Consequence: during the
sim, the rendered tube is shorter than the distance between parent and child
node — visually a transient gap that closes as the internode matures. The
post-sim finalization (simulator.py) snaps every length = length_target so the
exported geometry is always fully grown.
"""
from __future__ import annotations

import math

from palubicki.config import ElongationConfig
from palubicki.sim.tree import Tree


def shoot_extension(v_b: float, shoot_extension_max: float, vigor_ref: float) -> float:
    """Saturating physiological length response to BH flux.

    length = shoot_extension_max * (1 - exp(-v_b / vigor_ref))

    Small v_b is ~linear in resource; large v_b asymptotes to a finite annual
    shoot extension (a meristem rate limit, not an arbitrary clamp). Replaces the
    old top-down age_factor(birth_time) decay (#20).
    """
    if vigor_ref <= 0:
        return shoot_extension_max
    return shoot_extension_max * (1.0 - math.exp(-v_b / vigor_ref))


def update_lengths(tree: Tree, current_time: float, cfg: ElongationConfig) -> None:
    """Recompute Internode.length in-place via sigmoid ramp.

    length(t) = length_target * sigmoid((elapsed - tau) / (tau/2))
    where elapsed = max(0.0, current_time - birth_time) and tau = tau_years.

    No-op if cfg.enabled is False or cfg.tau_years <= 0.
    """
    if not cfg.enabled:
        return
    tau = cfg.tau_years
    if tau <= 0:
        return
    half_tau = tau / 2.0
    for iod in tree.all_internodes:
        elapsed = max(0.0, current_time - iod.birth_time)
        x = (elapsed - tau) / half_tau
        sigma = 1.0 / (1.0 + math.exp(-x))
        iod.length = iod.length_target * sigma
