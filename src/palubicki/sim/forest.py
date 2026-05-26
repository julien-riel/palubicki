# src/palubicki/sim/forest.py
from __future__ import annotations

from dataclasses import fields, replace
from typing import TYPE_CHECKING

import numpy as np

from palubicki.config import Config, EnvelopeConfig, ForestSeed

if TYPE_CHECKING:
    from palubicki.sim.markers import MarkerCloud
    from palubicki.sim.tree import Tree


_SECTION_FIELDS = {
    "envelope", "sim", "tropism", "phyllotaxy", "shedding", "geom", "light",
}


def per_tree_config(cfg: Config, seed_entry: ForestSeed, tree_index: int) -> Config:
    """Return a new Config: cfg with seed_entry.overrides applied (dotted keys) and
    envelope.center translated to seed_entry.position."""
    section_updates: dict[str, dict] = {s: {} for s in _SECTION_FIELDS}
    top_updates: dict[str, object] = {}

    for dotted, value in seed_entry.overrides.items():
        parts = dotted.split(".", 1)
        if len(parts) == 1:
            top_updates[parts[0]] = value
        else:
            section, key = parts
            if section not in _SECTION_FIELDS:
                from palubicki.config import ConfigError
                raise ConfigError(f"unknown section in override: {dotted!r}")
            section_updates[section][key] = value

    # Apply section overrides via replace()
    new_sections = {}
    for s in _SECTION_FIELDS:
        cur = getattr(cfg, s)
        updates = section_updates[s]
        if updates:
            new_sections[s] = replace(cur, **updates)
        else:
            new_sections[s] = cur

    # Translate envelope center to seed position (after overrides, so explicit
    # envelope.center in overrides wins if user did that)
    if "envelope.center" not in seed_entry.overrides:
        new_sections["envelope"] = replace(new_sections["envelope"], center=tuple(seed_entry.position))

    derived_seed = seed_entry.seed if seed_entry.seed is not None else (cfg.seed + tree_index)

    return Config(
        envelope=new_sections["envelope"],
        sim=new_sections["sim"],
        tropism=new_sections["tropism"],
        phyllotaxy=new_sections["phyllotaxy"],
        shedding=new_sections["shedding"],
        geom=new_sections["geom"],
        light=new_sections["light"],
        forest=cfg.forest,
        seed=top_updates.get("seed", derived_seed),
        output=cfg.output,
        log_level=cfg.log_level,
    )


def _envelope_aabb(env: EnvelopeConfig) -> tuple[np.ndarray, np.ndarray]:
    c = np.asarray(env.center, dtype=np.float64)
    if env.shape == "sphere":
        r = env.rx
        return c - r, c + r
    if env.shape == "ellipsoid":
        r = np.array([env.rx, env.ry, env.rz])
        return c - r, c + r
    if env.shape == "half_ellipsoid":
        amin = c - np.array([env.rx, 0.0, env.rz])
        amax = c + np.array([env.rx, env.ry, env.rz])
        return amin, amax
    if env.shape == "cone":
        amin = c - np.array([env.rx, 0.0, env.rz])
        amax = c + np.array([env.rx, env.ry, env.rz])
        return amin, amax
    raise ValueError(f"unknown envelope shape: {env.shape}")


def forest_light_bounds(envelopes: list[EnvelopeConfig], obstacles: list) -> tuple[np.ndarray, np.ndarray]:
    """Auto-fit AABB(union envelopes + obstacles) + V2-style sky margin
    (10% pad in x/z below/above, 10% below + 30% above in y)."""
    mins = []
    maxs = []
    for env in envelopes:
        amin, amax = _envelope_aabb(env)
        mins.append(amin)
        maxs.append(amax)
    for o in obstacles:
        amin, amax = o.aabb()
        mins.append(amin)
        maxs.append(amax)
    aabb_min = np.min(np.stack(mins), axis=0)
    aabb_max = np.max(np.stack(maxs), axis=0)
    extent = aabb_max - aabb_min
    origin = aabb_min - 0.1 * extent
    margin_top = np.array([0.1 * extent[0], 0.3 * extent[1], 0.1 * extent[2]])
    size = (aabb_max + margin_top) - origin
    return origin, size
