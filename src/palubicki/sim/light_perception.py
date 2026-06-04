# src/palubicki/sim/light_perception.py
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from palubicki.config import LightConfig, ShadowConfig
from palubicki.sim.light import LightGrid
from palubicki.sim.tree import Bud


@dataclass
class LightPerception:
    light_factor: dict[Bud, float] = field(default_factory=dict)
    gradient: dict[Bud, np.ndarray] = field(default_factory=dict)
    # Raw shadow-propagation exposure Q (#56), un-normalized. Populated only by
    # perceive_exposure; light_factor carries the normalized Q/C so the
    # shade-mortality / shade-avoidance thresholds stay on their [0,1] scale,
    # while this raw Q is the source for the BH vigor currency (scaled in the
    # simulator dispatch, Phase 3). Empty on the BHse / hemisphere path.
    exposure: dict[Bud, float] = field(default_factory=dict)


def perceive_light(
    buds: list[Bud],
    grid: LightGrid,
    cfg: LightConfig,
    *,
    seed: int,
) -> LightPerception:
    """Compute light_factor and gradient at each bud via hemispheric sampling.

    Fix #5: single batched ray-march across (B × n_rays) instead of B sequential calls.
    Per-bud RNG seeding is preserved (each bud spawns from the same SeedSequence as
    before) so the random directions stay identical.
    """
    result = LightPerception()
    if not buds:
        return result
    light_dir = np.asarray(cfg.light_direction, dtype=np.float64)
    ss = np.random.SeedSequence(seed)
    sub_seeds = ss.spawn(len(buds))
    seeds = [int(sub.generate_state(1)[0]) for sub in sub_seeds]
    positions = np.asarray([bud.position for bud in buds], dtype=np.float64)
    light_factors, gradients = grid.sample_hemisphere_batch(
        positions,
        n_rays=cfg.n_rays,
        light_direction=light_dir,
        k=cfg.k_absorption,
        seeds=seeds,
    )
    for i, bud in enumerate(buds):
        result.light_factor[bud] = float(light_factors[i])
        result.gradient[bud] = gradients[i]
    return result


def perceive_exposure(
    buds: list[Bud],
    grid: LightGrid,
    cfg: ShadowConfig,
    *,
    r_perception: float,
) -> LightPerception:
    """Shadow-propagation perception (#56): per-bud exposure Q + light gradient.

    The dual to :func:`perceive_light` for the shadow backend. Fills the SAME
    ``LightPerception`` struct so every downstream consumer is unchanged:
    ``exposure`` carries the raw Q (BH-currency source), ``light_factor`` the
    normalized ``Q / full_light_C`` (∈ [0, 1] for the calibrated shade signals),
    and ``gradient`` the light-gradient growth direction. Assumes ``grid.shadow``
    has already been rebuilt (:meth:`LightGrid.propagate_shadow`).
    """
    result = LightPerception()
    if not buds:
        return result
    positions = np.asarray([bud.position for bud in buds], dtype=np.float64)
    directions = np.asarray([bud.direction for bud in buds], dtype=np.float64)
    Q, gradients = grid.sample_exposure_batch(
        positions, directions, cfg=cfg, r_perception=r_perception,
    )
    C = float(cfg.full_light_C)
    for i, bud in enumerate(buds):
        q = float(Q[i])
        result.exposure[bud] = q
        result.light_factor[bud] = q / C if C > 0 else 0.0
        result.gradient[bud] = gradients[i]
    return result
