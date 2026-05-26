# src/palubicki/sim/light_perception.py
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from palubicki.config import LightConfig
from palubicki.sim.light import LightGrid
from palubicki.sim.tree import Bud


@dataclass
class LightPerception:
    light_factor: dict[Bud, float] = field(default_factory=dict)
    gradient: dict[Bud, np.ndarray] = field(default_factory=dict)


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
