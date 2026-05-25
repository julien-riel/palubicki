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
    """Compute light_factor and gradient at each bud via hemispheric sampling."""
    result = LightPerception()
    light_dir = np.asarray(cfg.light_direction, dtype=np.float64)
    ss = np.random.SeedSequence(seed)
    sub_seeds = ss.spawn(len(buds))
    for bud, sub in zip(buds, sub_seeds):
        per_bud_seed = int(sub.generate_state(1)[0])
        lf, grad = grid.sample_hemisphere(
            bud.position,
            n_rays=cfg.n_rays,
            light_direction=light_dir,
            k=cfg.k_absorption,
            seed=per_bud_seed,
        )
        result.light_factor[bud] = lf
        result.gradient[bud] = grad
    return result
