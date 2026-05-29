# src/palubicki/sim/simulator.py
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np

from palubicki.config import Config
from palubicki.sim.bh import allocate, compute_v_subtree
from palubicki.sim.bud_break_bias import compute_axis_positions, position_weight
from palubicki.sim.clock import Clock
from palubicki.sim.elongation import compute_target_with_age, update_lengths
from palubicki.sim.forest import Forest, all_active_buds, build_forest, forest_light_bounds
from palubicki.sim.light import LightGrid
from palubicki.sim.light_perception import perceive_light
from palubicki.sim.obstacles import any_contains, segment_blocked
from palubicki.sim.phyllotaxy import lateral_bud_directions, reserve_bud_directions
from palubicki.sim.radii import update_diameters_incremental
from palubicki.sim.sag import apply_sag
from palubicki.sim.shade_mortality import kill_shaded_buds
from palubicki.sim.shedding import record_qualities, shed_low_quality
from palubicki.sim.space_competition import perceive
from palubicki.sim.sympodial import promote_lateral_if_failing
from palubicki.sim.tree import Bud, BudState, Internode, Node, Tree
from palubicki.sim.tropisms import growth_direction

logger = logging.getLogger(__name__)

_ILEN_SALT = int.from_bytes(b"ilen", "big")


@dataclass
class _SubstepChain:
    """A single bud's substep chain: evolves over ``n`` steps until ``done``."""
    bud_old: Bud      # the original active bud (becomes DEAD after step 0)
    current: Bud      # the "growing tip" — initially ``bud_old``, then the latest terminal
    n: int            # planned number of substeps (from allocate())
    done: bool        # True once the chain breaks (U-turn / obstacle / dormant)


class _SimState:
    """Mutable counters shared across iterations.

    node_index is a global per-emission counter used for RNG salting (internode
    length jitter) and node identity. It is NOT used for phyllotaxy divergence —
    that is driven by the per-axis Bud.axis_node_ordinal (#24)."""
    def __init__(self):
        self.node_index = 0


def simulate(cfg: Config) -> Tree:
    """Single-tree entry point (V1/V2 backward-compat).
    Delegates to simulate_forest and returns trees[0]."""
    forest = simulate_forest(cfg)
    return forest.trees[0]


def simulate_forest(cfg: Config) -> Forest:
    forest = build_forest(cfg)
    if cfg.light.enabled:
        _init_light_grid(forest, cfg)
    no_new_streak = 0
    t0 = time.time()
    state = _SimState()
    clock = Clock(dt=cfg.sim.dt_years)
    for iteration in range(cfg.sim.num_iterations):
        clock.t = iteration * cfg.sim.dt_years
        if not any(t.active_buds for t in forest.trees):
            break
        if not clock.in_window(*cfg.sim.annual_growth_period):
            # Dormant season: age existing structure, emit nothing. Does NOT
            # count toward the no-growth early-stop (that is for saturation).
            _apply_temporal_dynamics(forest, cfg, clock.t)
            continue
        nodes_created = _iteration_step(forest, cfg, iteration, clock.t, state, t0)
        if nodes_created == 0:
            no_new_streak += 1
        else:
            no_new_streak = 0
        if no_new_streak >= 2:
            break

    # --- Phase 2D finalization ---
    # Snap every internode to its target length, recompute diameters and sag.
    if cfg.sim.elongation.enabled:
        for tree in forest.trees:
            for iod in tree.all_internodes:
                iod.length = iod.length_target
    for tree in forest.trees:
        update_diameters_incremental(tree, r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent)
    if cfg.sag.enabled:
        for tree in forest.trees:
            apply_sag(tree, cfg=cfg.sag)
    return forest


def _init_light_grid(forest: Forest, cfg: Config) -> None:
    """Create forest.light_grid and (in forest mode) auto-fit its bounds and
    voxelize obstacles into forest.obstacle_voxel_mask. One-shot setup."""
    forest.light_grid = LightGrid.from_config(cfg.light, cfg.envelope)
    # Adjust grid bounds for forest mode (auto-fit including obstacles)
    if cfg.light.grid_origin is None or cfg.light.grid_size is None:
        envs = [ptc.envelope for ptc in forest.per_tree_cfgs]
        origin, size = forest_light_bounds(envs, forest.obstacles)
        nx, ny, nz = cfg.light.grid_resolution
        forest.light_grid.origin = origin
        forest.light_grid.cell_size = size / np.array([nx, ny, nz], dtype=np.float64)
    # Voxelize obstacles into mask (one-shot)
    if forest.obstacles:
        mask = forest.obstacles[0].voxelize(forest.light_grid)
        for o in forest.obstacles[1:]:
            mask = mask | o.voxelize(forest.light_grid)
        forest.obstacle_voxel_mask = mask


def _perceive_forest_light(forest: Forest, union_buds, cfg: Config, iteration: int):
    """Rebuild the light grid from current geometry and perceive light for every
    active bud. Returns the light_info struct, or None when light is disabled."""
    light_grid = forest.light_grid
    if light_grid is None:
        return None
    light_grid.rebuild_from_forest(
        forest, cfg.light,
        r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent,
    )
    return perceive_light(
        union_buds, light_grid, cfg.light,
        seed=int(np.random.SeedSequence([cfg.seed, iteration]).generate_state(1)[0]),
    )


def _apply_shade_mortality(forest: Forest, light_info, cfg: Config) -> list[Bud]:
    """Phase 2B: kill buds whose light stays below threshold, prune them from
    each tree's active list, and return the refreshed union of active buds.

    Runs AFTER perceive_light populates light_factor and BEFORE marker perception
    / allocation so that dead buds do not consume markers or appear in the substep
    loop."""
    kill_shaded_buds(
        all_active_buds(forest), light_info.light_factor, cfg.sim.shade_mortality
    )
    for tree in forest.trees:
        tree.active_buds = [
            b for b in tree.active_buds if b.state is not BudState.DEAD
        ]
    return all_active_buds(forest)


def _compute_quality(forest: Forest, union_buds, res, light_info, cfg: Config) -> dict:
    """Combine marker-perception quality with the light factor and the per-axis
    bud-break bias. Returns a {bud: quality} dict."""
    if light_info is not None:
        quality = {b: res.quality[b] * light_info.light_factor[b] for b in union_buds}
    else:
        quality = dict(res.quality)

    # Bud-break bias: modulate lateral quality by position along parent axis.
    # Skipped entirely in the default (uniform / strength=0) case to avoid the
    # per-tree axis walk when the bias is off.
    bb = cfg.sim.bud_break_bias
    if bb.mode != "uniform" and bb.strength > 0.0:
        for tree in forest.trees:
            positions = compute_axis_positions(tree)
            for b, (node_index, axis_length) in positions.items():
                if b not in quality:
                    continue
                quality[b] = quality[b] * position_weight(
                    node_index, axis_length, bb.mode, bb.strength
                )
    return quality


def _iteration_step(forest: Forest, cfg: Config, iteration: int, t: float, state: _SimState, t0: float) -> int:
    """One simulation step on the whole forest. Returns total nodes created.

    For backward-compat: when len(trees)==1 and obstacles==[], this must produce
    bit-exactly the same evolution as V2's simulate() loop body."""
    union_buds = all_active_buds(forest)
    light_info = _perceive_forest_light(forest, union_buds, cfg, iteration)

    if light_info is not None and cfg.sim.shade_mortality.enabled:
        union_buds = _apply_shade_mortality(forest, light_info, cfg)

    res = perceive(
        union_buds, forest.markers,
        r_perception=cfg.sim.r_perception,
        theta_perception_deg=cfg.sim.theta_perception_deg,
    )

    quality = _compute_quality(forest, union_buds, res, light_info, cfg)

    new_node_positions: list[np.ndarray] = []
    nodes_created_this_step = 0
    for tree in forest.trees:
        created, positions = _grow_tree(
            tree, forest, cfg, iteration, t, state, res, light_info, quality
        )
        nodes_created_this_step += created
        new_node_positions.extend(positions)

    if new_node_positions:
        forest.markers.kill_near(np.array(new_node_positions), cfg.sim.r_kill)

    for tree in forest.trees:
        shed_low_quality(tree, cfg=cfg.shedding)

    _apply_temporal_dynamics(forest, cfg, t)

    logger.info(
        "[%.1fs] sim/iter %d/%d  year=%.2f  trees=%d  nodes_created=%d",
        time.time() - t0,
        iteration + 1, cfg.sim.num_iterations, t,
        len(forest.trees),
        nodes_created_this_step,
    )
    return nodes_created_this_step


def _grow_tree(
    tree: Tree, forest: Forest, cfg: Config, iteration: int, t: float, state: _SimState,
    res, light_info, quality: dict,
) -> tuple[int, list[np.ndarray]]:
    """Grow one tree by one iteration. Returns (nodes_created, new_positions).

    Runs the step-major substep loop: walks one substep level at a time across all
    bud chains, issuing ONE batched perceive()/light sample per level (see
    _reperceive_substep_terminals). This differs from a bud-major loop in two ways
    vs. the pre-refactor singleton path:
      - state.node_index assignments are interleaved across chains within each
        substep level (not all-of-A before any-of-B). This is fine for phyllotaxy:
        divergence azimuths are driven by the PER-AXIS Bud.axis_node_ordinal, not
        the global node_index (#24), so each axis advances by a constant step
        regardless of interleaving. node_index still salts the internode-length
        RNG, so its ordering causes only minor length-jitter drift vs. pre-refactor
        goldens. The qualitative biology (apical dominance, light-driven curvature,
        marker competition) is preserved.
      - The batched perceive() introduces cross-bud competition between substep
        terminals (closest-bud claims each marker), bringing substep perception in
        line with the main-loop perception (which already competes across all buds).
    """
    new_positions: list[np.ndarray] = []
    nodes_created = 0

    if cfg.sim.sympodial.enabled:
        promote_lateral_if_failing(tree, quality, cfg.sim.sympodial)
    v_subtree = compute_v_subtree(tree, quality)
    n_by_bud = allocate(
        tree, quality=quality,
        alpha=cfg.sim.alpha_basipetal, lambda_apical=cfg.sim.lambda_apical,
        v_subtree=v_subtree,
    )
    # Paper BHse: 1 internode per bud per iteration. Cap any allocation
    # surplus; the leftover is implicitly "lost" rather than letting one
    # bud avalanche through the envelope in a single year.
    cap = int(cfg.sim.n_substeps_max)
    if cap >= 1:
        n_by_bud = {b: min(n, cap) for b, n in n_by_bud.items()}
    record_qualities(tree, v_subtree=v_subtree)

    new_active: list[Bud] = []
    chains: list[_SubstepChain] = []
    for bud_old in list(tree.active_buds):
        n = n_by_bud.get(bud_old, 0)
        v_perc = res.direction[bud_old]
        v_perc_norm = float(np.linalg.norm(v_perc))
        if n < 1 or v_perc_norm < 1e-12:
            bud_old.state = BudState.DORMANT
            new_active.append(bud_old)
            continue
        chains.append(_SubstepChain(bud_old=bud_old, current=bud_old, n=n, done=False))

    max_n = max((c.n for c in chains), default=0)
    for step in range(max_n):
        # Stage 1: per-chain emission for this substep level, in tree.active_buds order.
        step_terminals: list[Bud] = []
        step_chains: list[_SubstepChain] = []
        step_parents: list[Bud] = []     # the "current" bud each terminal grew from (for re_perceive=False inheritance)
        for chain in chains:
            if chain.done or chain.n <= step:
                continue
            cur = chain.current
            light_grad = light_info.gradient[cur] if light_info else None
            is_main = (cur is cur.parent_node.terminal_bud)
            d = growth_direction(
                v_perception=res.direction[cur],
                current_direction=cur.direction,
                cfg=cfg.tropism,
                is_main_axis=is_main,
                light_gradient=light_grad,
                axis_order=cur.axis_order,
            )
            # Fix #1: U-turn check on the BLENDED growth direction. After tropisms
            # have mixed with perception, a sharp fold-back means the bud is folding
            # against the envelope — kill it. Catches envelope-boundary curls without
            # fighting gravitropism.
            if float(np.dot(d, cur.direction)) < cfg.sim.cos_min_perception:
                cur.state = BudState.DORMANT
                new_active.append(cur)
                chain.done = True
                continue
            target = _internode_target(cur, cfg, iteration, t, state)
            # Node placed at FINAL geometric position. During sim, length
            # ramps from 0 toward target (transient visual gap closes by
            # the finalization snap at end of simulate()).
            new_pos = cur.position + d * target

            # V3: obstacle blocking
            if forest.obstacles:
                if segment_blocked(cur.position, new_pos, forest.obstacles):
                    cur.state = BudState.DORMANT
                    new_active.append(cur)
                    chain.done = True
                    continue
                if any_contains(new_pos, forest.obstacles):
                    cur.state = BudState.DEAD
                    chain.done = True
                    continue

            new_node, terminal = _emit_node(
                cur, d, new_pos, target, is_main, light_info, tree, cfg, t, state
            )
            new_positions.append(new_pos)
            nodes_created += 1

            new_active.extend(new_node.lateral_buds)

            if step + 1 < chain.n:
                step_terminals.append(terminal)
                step_chains.append(chain)
                step_parents.append(cur)
            else:
                new_active.append(terminal)
                chain.done = True

        # Stage 2: batched perception + light for substep terminals.
        if step_terminals:
            _reperceive_substep_terminals(
                step_terminals, step_chains, step_parents, new_active,
                forest, cfg, light_info, res, iteration, step,
            )

    tree.active_buds = [b for b in new_active if b.state != BudState.DEAD]
    return nodes_created, new_positions


def _internode_target(cur: Bud, cfg: Config, iteration: int, t: float, state: _SimState) -> float:
    """Length the new internode should reach: base length (optionally jittered)
    passed through the age-dependent elongation ramp.

    The jitter RNG is salted by (seed, _ILEN_SALT, iteration, node_index) so the
    draw is reproducible and independent of perception/light ordering."""
    base_length = cfg.sim.internode_length
    if cfg.sim.internode_length_jitter > 0:
        # iteration is the integer loop index, used only for RNG seeding (not biological time).
        ss = np.random.SeedSequence(
            [cfg.seed, _ILEN_SALT, iteration, state.node_index]
        )
        rng = np.random.default_rng(ss.generate_state(1)[0])
        factor = max(0.5, min(1.5, rng.normal(1.0, cfg.sim.internode_length_jitter)))
        base_length = cfg.sim.internode_length * factor
    return compute_target_with_age(
        base_length=base_length,
        birth_time=t,
        total_years=cfg.sim.max_simulation_years,
        cfg=cfg.sim.elongation,
    )


def _emit_node(
    cur: Bud, d: np.ndarray, new_pos: np.ndarray, target: float, is_main: bool,
    light_info, tree: Tree, cfg: Config, t: float, state: _SimState,
) -> tuple[Node, Bud]:
    """Create the node + internode + terminal/lateral/reserve buds for one substep
    emission. Mutates tree.all_internodes, state.node_index, cur.parent_node's child
    lists, and marks ``cur`` DEAD. Returns (new_node, terminal_bud)."""
    lf = (
        float(light_info.light_factor.get(cur, 1.0))
        if light_info is not None else 1.0
    )
    new_node = Node(position=new_pos)
    iod = Internode(
        parent_node=cur.parent_node,
        child_node=new_node,
        length=(0.0 if cfg.sim.elongation.enabled else target),
        is_main_axis=is_main,
        window=cfg.shedding.window,
        light_factor=lf,
        birth_time=t,
        length_target=target,
    )
    cur.parent_node.children_internodes.append(iod)
    new_node.parent_internode = iod
    tree.all_internodes.append(iod)

    # The terminal continues ``cur``'s axis, so it carries the next phyllotactic
    # ordinal along that lineage.
    terminal = Bud(
        position=new_pos.copy(), direction=d,
        axis_order=cur.axis_order, parent_node=new_node,
        low_quality_steps=cur.low_quality_steps,
        low_light_steps=cur.low_light_steps,
        axis_node_ordinal=cur.axis_node_ordinal + 1,
    )
    new_node.terminal_bud = terminal

    # Phyllotaxy azimuth is driven by the PER-AXIS ordinal (cur.axis_node_ordinal),
    # not the global node_index (#24). The global counter is interleaved across
    # chains by the step-major substep loop, so feeding it here scrambled the
    # divergence delivered along any single axis. node_index is still bumped below
    # for RNG salting (internode length jitter) / identity only.
    axis_ord = cur.axis_node_ordinal
    lateral_dirs = lateral_bud_directions(
        d, cfg.phyllotaxy,
        node_index=axis_ord,
        seed=cfg.seed,
        axis_order=cur.axis_order,
    )
    state.node_index += 1
    # Laterals each begin a NEW axis → their phyllotactic ordinal restarts at 0
    # (the Bud default), so each branch axis advances divergence from its own base.
    for ld in lateral_dirs:
        lat = Bud(
            position=new_pos.copy(), direction=ld,
            axis_order=cur.axis_order + 1, parent_node=new_node,
        )
        new_node.lateral_buds.append(lat)

    # Phase 2B: emit RESERVE buds (not added to active_buds).
    if cfg.phyllotaxy.dormant_reserve_count > 0:
        reserve_dirs = reserve_bud_directions(
            d, cfg.phyllotaxy,
            node_index=axis_ord,
            seed=cfg.seed,
            count=cfg.phyllotaxy.dormant_reserve_count,
        )
        for rd in reserve_dirs:
            rbud = Bud(
                position=new_pos.copy(), direction=rd,
                axis_order=cur.axis_order + 1, parent_node=new_node,
                state=BudState.RESERVE,
            )
            new_node.dormant_reserve_buds.append(rbud)

    cur.state = BudState.DEAD
    return new_node, terminal


def _reperceive_substep_terminals(
    step_terminals: list[Bud], step_chains: list[_SubstepChain], step_parents: list[Bud],
    new_active: list[Bud], forest: Forest, cfg: Config, light_info, res,
    iteration: int, step: int,
) -> None:
    """Stage 2 of the substep loop: refresh perception (and light) for the terminals
    created at this substep level, then advance or close each chain.

    With re_perceive_per_substep, issues ONE batched perceive() + ONE batched
    hemisphere light sample for all terminals; otherwise each terminal inherits its
    parent's perception. Mutates res, light_info, chain.current/done, term.state, and
    appends newly-dormant terminals to new_active."""
    light_grid = forest.light_grid
    if cfg.sim.re_perceive_per_substep:
        sub_result = perceive(
            step_terminals, forest.markers,
            r_perception=cfg.sim.r_perception,
            theta_perception_deg=cfg.sim.theta_perception_deg,
        )
        for term in step_terminals:
            res.direction[term] = sub_result.direction[term]
            res.quality[term] = sub_result.quality[term]
        if light_grid is not None and light_info is not None:
            positions = np.asarray([t.position for t in step_terminals], dtype=np.float64)
            # Match the scalar substep seed: SeedSequence([cfg.seed, iteration, step+1])
            # is independent of bud, so all terminals at this substep level share it
            # — identical to the original per-call behavior.
            seed_step = int(
                np.random.SeedSequence([cfg.seed, iteration, step + 1]).generate_state(1)[0]
            )
            seeds = [seed_step] * len(step_terminals)
            lfs, grads = light_grid.sample_hemisphere_batch(
                positions,
                n_rays=cfg.light.n_rays,
                light_direction=np.asarray(cfg.light.light_direction, dtype=np.float64),
                k=cfg.light.k_absorption,
                seeds=seeds,
            )
            for i, term in enumerate(step_terminals):
                light_info.light_factor[term] = float(lfs[i])
                light_info.gradient[term] = grads[i]
        # Zero-direction → mark dormant + close the chain (matches original break).
        for chain, term in zip(step_chains, step_terminals, strict=True):
            if np.linalg.norm(res.direction[term]) < 1e-12:
                term.state = BudState.DORMANT
                new_active.append(term)
                chain.done = True
            else:
                chain.current = term
    else:
        # re_perceive_per_substep=False → each terminal inherits perception
        # from its parent ``cur`` (same as the original else-branch).
        for chain, parent, term in zip(step_chains, step_parents, step_terminals, strict=True):
            res.direction[term] = res.direction.get(parent, np.zeros(3))
            res.quality[term] = res.quality.get(parent, 0)
            if light_info is not None:
                light_info.light_factor[term] = light_info.light_factor.get(parent, 1.0)
                light_info.gradient[term] = light_info.gradient.get(parent, np.zeros(3))
            chain.current = term


def _apply_temporal_dynamics(forest: Forest, cfg: Config, t: float) -> None:
    """Per-iteration aging updates. Order matters: lengths first (sag reads
    load = length × diameter²), diameters next (sag reads diameter), sag last."""
    if cfg.sim.elongation.enabled:
        for tree in forest.trees:
            update_lengths(tree, current_time=t, cfg=cfg.sim.elongation)
    for tree in forest.trees:
        update_diameters_incremental(tree, r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent)
    if cfg.sag.enabled:
        for tree in forest.trees:
            apply_sag(tree, cfg=cfg.sag)
