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


def perceive_exposure_skyview(
    buds: list[Bud],
    grid: LightGrid,
    light_cfg: LightConfig,
    shadow_cfg: ShadowConfig,
    *,
    seed: int,
) -> LightPerception:
    """Sky-view exposure for the shadow backend (#56): Q from the #37 hemisphere
    transmission (open-sky fraction), gradient toward the brightest sky.

    The fix for the downward-shadow inversion: a bud's exposure is how much open
    sky its hemisphere sees (the calibrated Beer-Lambert ray-march of
    :meth:`LightGrid.sample_hemisphere_batch`), NOT just the shadow directly
    overhead. A lower-edge branch open to the side therefore reads high Q, keeps
    vigor, and grows out — so the crown widens toward the base instead of
    collapsing into an inverted feather-duster. Assumes ``grid.lai`` is current
    (rebuilt upstream). Mirrors :func:`perceive_light`'s sampling/seeding so the
    direction signal is identical, but packages the result as the exposure struct
    the shadow dispatch consumes (``exposure`` = Q on the [0, C] scale).
    """
    result = LightPerception()
    if not buds:
        return result
    light_dir = np.asarray(light_cfg.light_direction, dtype=np.float64)
    ss = np.random.SeedSequence(seed)
    seeds = [int(sub.generate_state(1)[0]) for sub in ss.spawn(len(buds))]
    positions = np.asarray([bud.position for bud in buds], dtype=np.float64)
    light_factors, gradients = grid.sample_hemisphere_batch(
        positions, n_rays=light_cfg.n_rays, light_direction=light_dir,
        k=light_cfg.k_absorption, seeds=seeds,
    )
    C = float(shadow_cfg.full_light_C)
    for i, bud in enumerate(buds):
        lf = float(light_factors[i])            # mean transmission ∈ [0, 1]
        result.light_factor[bud] = lf
        result.exposure[bud] = lf * C            # Q on the [0, C] scale
        result.gradient[bud] = gradients[i]
    return result
