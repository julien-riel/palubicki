# src/palubicki/sim/simulator.py
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np

_ILEN_SALT = int.from_bytes(b"ilen", "big")

from palubicki.config import Config
from palubicki.sim.bh import allocate, compute_v_subtree
from palubicki.sim.bud_break_bias import compute_axis_positions, position_weight
from palubicki.sim.forest import Forest, all_active_buds, build_forest, forest_light_bounds
from palubicki.sim.light import LightGrid
from palubicki.sim.light_perception import perceive_light
from palubicki.sim.phyllotaxy import lateral_bud_directions, reserve_bud_directions
from palubicki.sim.radii import update_diameters_incremental
from palubicki.sim.sag import apply_sag
from palubicki.sim.shade_mortality import kill_shaded_buds
from palubicki.sim.shedding import record_qualities, shed_low_quality
from palubicki.sim.space_competition import perceive
from palubicki.sim.tree import Bud, BudState, Internode, Node, Tree
from palubicki.sim.elongation import compute_target_with_age, update_lengths
from palubicki.sim.sympodial import promote_lateral_if_failing
from palubicki.sim.tropisms import growth_direction


@dataclass
class _SubstepChain:
    """A single bud's substep chain: evolves over ``n`` steps until ``done``."""
    bud_old: Bud      # the original active bud (becomes DEAD after step 0)
    current: Bud      # the "growing tip" — initially ``bud_old``, then the latest terminal
    n: int            # planned number of substeps (from allocate())
    done: bool        # True once the chain breaks (U-turn / obstacle / dormant)

logger = logging.getLogger(__name__)


def simulate(cfg: Config) -> Tree:
    """Single-tree entry point (V1/V2 backward-compat).
    Delegates to simulate_forest and returns trees[0]."""
    forest = simulate_forest(cfg)
    return forest.trees[0]


def simulate_forest(cfg: Config) -> Forest:
    forest = build_forest(cfg)
    if cfg.light.enabled:
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
    no_new_streak = 0
    t0 = time.time()
    state = _SimState()
    for iteration in range(cfg.sim.max_iterations):
        if not any(t.active_buds for t in forest.trees):
            break
        nodes_created = _iteration_step(forest, cfg, iteration, state, t0)
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


class _SimState:
    """Mutable counters shared across iterations: node_index for phyllotaxy."""
    def __init__(self):
        self.node_index = 0


def _iteration_step(forest: Forest, cfg: Config, iteration: int, state: _SimState, t0: float) -> int:
    """One simulation step on the whole forest. Returns total nodes created.

    For backward-compat: when len(trees)==1 and obstacles==[], this must produce
    bit-exactly the same evolution as V2's simulate() loop body."""
    light_grid = forest.light_grid
    union_buds = all_active_buds(forest)

    if light_grid is not None:
        light_grid.rebuild_from_forest(
            forest, cfg.light,
            r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent,
        )
        light_info = perceive_light(
            union_buds, light_grid, cfg.light,
            seed=int(np.random.SeedSequence([cfg.seed, iteration]).generate_state(1)[0]),
        )
    else:
        light_info = None

    # Phase 2B: shade-induced bud mortality runs AFTER perceive_light populates
    # light_factor and BEFORE marker perception / allocation so that dead buds
    # do not consume markers or appear in the substep loop.
    if light_info is not None and cfg.sim.shade_mortality.enabled:
        kill_shaded_buds(
            union_buds, light_info.light_factor, cfg.sim.shade_mortality
        )
        for tree in forest.trees:
            tree.active_buds = [
                b for b in tree.active_buds if b.state is not BudState.DEAD
            ]
        union_buds = all_active_buds(forest)

    res = perceive(
        union_buds, forest.markers,
        r_perception=cfg.sim.r_perception,
        theta_perception_deg=cfg.sim.theta_perception_deg,
    )

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

    new_node_positions: list[np.ndarray] = []
    nodes_created_this_step = 0

    for tree in forest.trees:
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

        # Step-major substep loop. The original code was bud-major (each bud's n substeps
        # in sequence), with each substep calling perceive() and sample_hemisphere() with
        # a single bud — paying the Python setup cost B-times. Here we walk one substep
        # level at a time across all chains, then issue ONE batched perceive() and ONE
        # sample_hemisphere_batch() for the new substep terminals. Two consequences vs.
        # the original bud-major path:
        #   - state.node_index assignments are interleaved across chains within each
        #     substep level (not all-of-A before any-of-B), so lateral phyllotaxy angles
        #     at substep-created nodes differ → small tree-shape drift vs. pre-refactor
        #     goldens. The qualitative biology (apical dominance, light-driven curvature,
        #     marker competition) is preserved.
        #   - The batched perceive() introduces cross-bud competition between substep
        #     terminals (closest-bud claims each marker). The previous singleton path had
        #     no such competition. This brings substep perception in line with the main-
        #     loop perception (which already competes across all active buds).
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
                base_length = cfg.sim.internode_length
                if cfg.sim.internode_length_jitter > 0:
                    ss = np.random.SeedSequence(
                        [cfg.seed, _ILEN_SALT, iteration, state.node_index]
                    )
                    rng = np.random.default_rng(ss.generate_state(1)[0])
                    factor = max(0.5, min(1.5, rng.normal(1.0, cfg.sim.internode_length_jitter)))
                    base_length = cfg.sim.internode_length * factor
                target = compute_target_with_age(
                    base_length=base_length,
                    birth_iteration=iteration,
                    max_iterations=cfg.sim.max_iterations,
                    cfg=cfg.sim.elongation,
                )
                # Node placed at FINAL geometric position. During sim, length
                # ramps from 0 toward target (transient visual gap closes by
                # the finalization snap at end of simulate()).
                new_pos = cur.position + d * target

                # V3: obstacle blocking
                if forest.obstacles:
                    from palubicki.sim.obstacles import segment_blocked, any_contains
                    if segment_blocked(cur.position, new_pos, forest.obstacles):
                        cur.state = BudState.DORMANT
                        new_active.append(cur)
                        chain.done = True
                        continue
                    if any_contains(new_pos, forest.obstacles):
                        cur.state = BudState.DEAD
                        chain.done = True
                        continue

                new_node = Node(position=new_pos)
                lf = (
                    float(light_info.light_factor.get(cur, 1.0))
                    if light_info is not None else 1.0
                )
                iod = Internode(
                    parent_node=cur.parent_node,
                    child_node=new_node,
                    length=(0.0 if cfg.sim.elongation.enabled else target),
                    is_main_axis=is_main,
                    window=cfg.shedding.window,
                    light_factor=lf,
                    birth_iteration=iteration,
                    length_target=target,
                )
                cur.parent_node.children_internodes.append(iod)
                new_node.parent_internode = iod
                tree.all_internodes.append(iod)
                new_node_positions.append(new_pos)
                nodes_created_this_step += 1

                terminal = Bud(
                    position=new_pos.copy(), direction=d,
                    axis_order=cur.axis_order, parent_node=new_node,
                    low_quality_steps=cur.low_quality_steps,
                    low_light_steps=cur.low_light_steps,
                )
                new_node.terminal_bud = terminal

                node_idx = state.node_index
                lateral_dirs = lateral_bud_directions(
                    d, cfg.phyllotaxy,
                    node_index=node_idx,
                    seed=cfg.seed,
                    axis_order=cur.axis_order,
                )
                state.node_index += 1
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
                        node_index=node_idx,
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

                new_active.extend(new_node.lateral_buds)
                cur.state = BudState.DEAD

                if step + 1 < chain.n:
                    step_terminals.append(terminal)
                    step_chains.append(chain)
                    step_parents.append(cur)
                else:
                    new_active.append(terminal)
                    chain.done = True

            # Stage 2: batched perception + light for substep terminals.
            if step_terminals:
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
                    for chain, term in zip(step_chains, step_terminals):
                        if np.linalg.norm(res.direction[term]) < 1e-12:
                            term.state = BudState.DORMANT
                            new_active.append(term)
                            chain.done = True
                        else:
                            chain.current = term
                else:
                    # re_perceive_per_substep=False → each terminal inherits perception
                    # from its parent ``cur`` (same as the original else-branch).
                    for chain, parent, term in zip(step_chains, step_parents, step_terminals):
                        res.direction[term] = res.direction.get(parent, np.zeros(3))
                        res.quality[term] = res.quality.get(parent, 0)
                        if light_info is not None:
                            light_info.light_factor[term] = light_info.light_factor.get(parent, 1.0)
                            light_info.gradient[term] = light_info.gradient.get(parent, np.zeros(3))
                        chain.current = term

        tree.active_buds = [b for b in new_active if b.state != BudState.DEAD]

    if new_node_positions:
        forest.markers.kill_near(np.array(new_node_positions), cfg.sim.r_kill)

    for tree in forest.trees:
        shed_low_quality(tree, cfg=cfg.shedding)

    # --- Phase 2D: per-iteration temporal dynamics ---
    # Order matters: lengths first (sag reads load = length × diameter²),
    # diameters next (sag reads diameter), sag last.
    if cfg.sim.elongation.enabled:
        for tree in forest.trees:
            update_lengths(tree, current_iteration=iteration, cfg=cfg.sim.elongation)
    for tree in forest.trees:
        update_diameters_incremental(tree, r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent)
    if cfg.sag.enabled:
        for tree in forest.trees:
            apply_sag(tree, cfg=cfg.sag)

    logger.info(
        "[%.1fs] sim/iter %d/%d  trees=%d  nodes_created=%d",
        time.time() - t0,
        iteration + 1, cfg.sim.max_iterations,
        len(forest.trees),
        nodes_created_this_step,
    )
    return nodes_created_this_step
