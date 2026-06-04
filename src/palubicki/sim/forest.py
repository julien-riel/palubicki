# src/palubicki/sim/forest.py
from __future__ import annotations

from dataclasses import dataclass, fields, replace

import numpy as np

from palubicki.config import (
    _SECTION_TYPES,
    Config,
    ConfigError,
    EnvelopeConfig,
    ForestSeed,
    _coerce,
    _load_packaged_species,
)
from palubicki.sim.envelope import points_inside, sample_markers
from palubicki.sim.markers import MarkerCloud
from palubicki.sim.obstacles import build_obstacles, filter_markers
from palubicki.sim.tree import Bud, Node, Tree

_SECTION_FIELDS = {
    "envelope", "sim", "tropism", "phyllotaxy", "shedding", "geom", "light", "shadow", "sag",
}


def per_tree_config(cfg: Config, seed_entry: ForestSeed, tree_index: int) -> Config:
    """Return a new Config: cfg with species preset (if any) + seed_entry.overrides
    applied (dotted keys) and envelope.center translated to seed_entry.position.

    Per-section, the current values, the species preset, and the per-seed
    overrides are merged into one dict and built through the shared recursive
    ``_coerce`` loader, so nested-dataclass / sequence coercion matches
    single-tree ``load_config`` exactly (no subset to forget)."""
    preset = _load_packaged_species(seed_entry.species) if seed_entry.species is not None else {}

    section_updates: dict[str, dict] = {s: {} for s in _SECTION_FIELDS}
    top_updates: dict[str, object] = {}
    for dotted, value in seed_entry.overrides.items():
        parts = dotted.split(".", 1)
        if len(parts) == 1:
            top_updates[parts[0]] = value
        else:
            section, key = parts
            if section not in _SECTION_FIELDS:
                raise ConfigError(f"unknown section in override: {dotted!r}")
            section_updates[section][key] = value

    new_sections: dict = {}
    for section_name, type_ in _SECTION_TYPES.items():
        cur_section = getattr(cfg, section_name)
        merged = {f.name: getattr(cur_section, f.name) for f in fields(type_)}
        merged.update(preset.get(section_name, {}) or {})
        merged.update(section_updates[section_name])
        new_sections[section_name] = _coerce(type_, merged, path=section_name)

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
        shadow=new_sections["shadow"],
        sag=new_sections["sag"],
        forest=cfg.forest,
        seed=top_updates.get("seed", derived_seed),
        exposure=top_updates.get("exposure", cfg.exposure),
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


@dataclass
class Forest:
    trees: list[Tree]
    seeds: list
    obstacles: list
    per_tree_cfgs: list
    markers: MarkerCloud
    light_grid: object | None = None
    obstacle_voxel_mask: np.ndarray | None = None


def all_active_buds(forest: Forest) -> list[Bud]:
    """Flatten active buds across trees in (tree_index, bud_index_in_tree) order."""
    out: list[Bud] = []
    for tree in forest.trees:
        out.extend(tree.active_buds)
    return out


def build_forest(cfg: Config) -> Forest:
    """Build the initial Forest from cfg.

    - If cfg.forest.seeds is empty, create one tree using cfg.envelope as-is.
    - Otherwise, derive a per_tree_config for each seed; sample its markers.
    - Concatenate all markers and filter via obstacles.
    - Light grid is created LATER (in simulator) if cfg.light.enabled.
    """
    obstacles = build_obstacles(cfg.forest)
    seeds_input = cfg.forest.seeds
    if not seeds_input:
        # Single-tree mode: one synthetic seed at envelope.center
        synthetic_seed = ForestSeed(position=tuple(cfg.envelope.center))
        seeds_list = [synthetic_seed]
        per_tree_cfgs = [cfg]
    else:
        seeds_list = list(seeds_input)
        per_tree_cfgs = [per_tree_config(cfg, s, i) for i, s in enumerate(seeds_list)]

    # Sample markers per-tree using each tree's own RNG/envelope
    marker_chunks: list[np.ndarray] = []
    trees: list[Tree] = []
    for _tree_index, ptc in enumerate(per_tree_cfgs):
        rng = np.random.default_rng(ptc.seed)
        marker_chunks.append(sample_markers(ptc.envelope, rng))

        # Build root bud at seed position (y forced to 0, matching V2 simulate)
        root_pos = np.array([ptc.envelope.center[0], 0.0, ptc.envelope.center[2]], dtype=float)
        root = Node(position=root_pos)
        bud = Bud(
            position=root_pos.copy(),
            direction=np.array([0.0, 1.0, 0.0]),
            axis_order=0,
            parent_node=root,
        )
        root.terminal_bud = bud
        trees.append(Tree(root=root, active_buds=[bud]))

    all_markers = np.concatenate(marker_chunks, axis=0) if marker_chunks else np.zeros((0, 3))
    all_markers = _thin_overlaps(all_markers, per_tree_cfgs, cfg.seed)
    filtered = filter_markers(all_markers, obstacles)
    cloud = MarkerCloud(filtered)

    return Forest(
        trees=trees,
        seeds=seeds_list,
        obstacles=obstacles,
        per_tree_cfgs=per_tree_cfgs,
        markers=cloud,
    )


def _thin_overlaps(markers: np.ndarray, per_tree_cfgs: list, seed: int) -> np.ndarray:
    """Flatten the marker density of overlapping envelopes to a uniform union.

    Each tree samples ``marker_count`` markers inside its own envelope, so where
    two envelopes overlap the concatenated cloud has additive density (~m× for m
    overlapping envelopes). Markers are attractors, so the inner-facing (overlap)
    side of each crown gets a density bonus and the crowns grow *toward* each other
    — anti-crown-shyness (#41). We restore uniform density by keeping each marker
    with probability ``1 / m``, where ``m`` is the number of envelopes that contain
    it: the overlap region then holds one envelope's worth of markers, shared by the
    competing trees (true depletion → crown shyness), not m envelopes' worth.

    Single-envelope forests have m≡1 everywhere, so this is a no-op (the marker
    cloud — and thus a lone tree — is byte-for-byte unchanged)."""
    if len(per_tree_cfgs) < 2 or len(markers) == 0:
        return markers
    membership = np.zeros(len(markers), dtype=np.int64)
    for ptc in per_tree_cfgs:
        membership += points_inside(ptc.envelope, markers).astype(np.int64)
    # Every marker lies inside the envelope that sampled it, so membership >= 1;
    # clamp guards against a float round-trip leaving a boundary marker at 0.
    membership = np.maximum(membership, 1)
    rng = np.random.default_rng(seed)
    keep = rng.random(len(markers)) < (1.0 / membership)
    return markers[keep]


def forest_light_bounds(envelopes: list[EnvelopeConfig], obstacles: list) -> tuple[np.ndarray, np.ndarray]:
    """Auto-fit AABB(union envelopes + obstacles) + V2-style sky margin
    (10% pad in x/z below/above, 10% below + 50% above in y). The top y-margin
    is generous so overshooting leaders still fall inside the grid AABB (#FIX G);
    it must match _autofit_bounds in light.py."""
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
    margin_top = np.array([0.1 * extent[0], 0.5 * extent[1], 0.1 * extent[2]])
    size = (aabb_max + margin_top) - origin
    return origin, size
