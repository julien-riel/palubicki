"""Progressive internode elongation (S-curve) + age_factor on target length.

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


def compute_target_with_age(
    base_length: float,
    birth_iteration: int,
    max_iterations: int,
    cfg: ElongationConfig,
) -> float:
    """target_length = base_length × age_factor(birth_iteration)."""
    if not cfg.enabled or max_iterations <= 0:
        return base_length
    decay = cfg.age_factor_decay
    if decay <= 0:
        return base_length
    t_norm = min(1.0, birth_iteration / max_iterations)
    base = math.exp(-decay * t_norm)
    base_at_one = math.exp(-decay)
    factor = (
        cfg.age_factor_min
        + (1.0 - cfg.age_factor_min) * (base - base_at_one) / (1.0 - base_at_one)
    )
    return base_length * factor
