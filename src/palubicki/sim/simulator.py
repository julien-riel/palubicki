# src/palubicki/sim/simulator.py
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import numpy as np

from palubicki.config import Config
from palubicki.sim.bh import allocate, compute_v_subtree
from palubicki.sim.bud_break_bias import compute_axis_positions, position_weight
from palubicki.sim.caducity import advance_leaf_states
from palubicki.sim.clock import Clock
from palubicki.sim.elongation import shoot_extension, update_lengths
from palubicki.sim.forest import Forest, all_active_buds, build_forest, forest_light_bounds
from palubicki.sim.light import LightGrid, _resolution_for
from palubicki.sim.light_perception import perceive_light
from palubicki.sim.obstacles import any_contains, segment_blocked
from palubicki.sim.phyllotaxy import (
    lateral_bud_directions,
    leaf_azimuths,
    reserve_bud_directions,
)
from palubicki.sim.radii import update_diameters_incremental
from palubicki.sim.sag import apply_sag
from palubicki.sim.shade_avoidance import lateral_break_probability
from palubicki.sim.shade_mortality import kill_shaded_buds
from palubicki.sim.shedding import record_qualities, shed_low_quality
from palubicki.sim.space_competition import perceive
from palubicki.sim.sympodial import promote_lateral_if_failing
from palubicki.sim.tree import Bud, BudState, Internode, Leaf, LeafState, Node, Tree
from palubicki.sim.tropisms import growth_direction, spray_plane_normal_from_direction

if TYPE_CHECKING:
    from palubicki.sim.debug_capture import DebugCollector

logger = logging.getLogger(__name__)

_ILEN_SALT = int.from_bytes(b"ilen", "big")
_SHADE_SALT = int.from_bytes(b"shav", "big")

# One-time guard for the out-of-grid overshoot warning (#FIX G). Set True after the
# first warning so a leader that has grown past the sky margin is surfaced once,
# not spammed every iteration.
_OVERSHOOT_WARNED = False


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


def simulate_forest(cfg: Config, collector: DebugCollector | None = None) -> Forest:
    """Run the full multi-tree simulation. If *collector* is given it receives a
    ``capture_static`` call once and one ``capture_frame`` call per executed
    iteration (dormant-season aging or growth step) for the editor's debug
    overlay (#29). The collector only reads forest state, so passing one does not
    perturb the deterministic evolution."""
    forest = build_forest(cfg)
    if collector is not None:
        collector.capture_static(forest, cfg)
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
        activity = clock.activity(
            *cfg.sim.annual_growth_period, cfg.sim.growth_period_shoulder
        )
        if activity <= 0.0:
            # Dormant season: age existing structure, emit nothing. Does NOT
            # count toward the no-growth early-stop (that is for saturation).
            # With growth_period_shoulder == 0 this is byte-identical to the
            # legacy ``not clock.in_window(...)`` gate (#65).
            _apply_temporal_dynamics(forest, cfg, clock.t)
            if collector is not None:
                collector.capture_frame(forest, clock.t)
            continue
        nodes_created = _iteration_step(forest, cfg, iteration, clock.t, state, t0, activity)
        if collector is not None:
            collector.capture_frame(forest, clock.t)
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
        update_diameters_incremental(
            tree, r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent,
            vigor_ref=cfg.sim.vigor_ref, vigor_diameter_gain=cfg.sim.vigor_diameter_gain,
        )
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
        # Mirror LightGrid.from_config's scale-aware derivation (#65): the forest
        # size differs from the single-env autofit, so re-derive resolution and
        # reallocate the LAI array to match.
        nx, ny, nz = _resolution_for(cfg.light, size)
        forest.light_grid.origin = origin
        forest.light_grid.cell_size = size / np.array([nx, ny, nz], dtype=np.float64)
        forest.light_grid.resolution = (nx, ny, nz)
        forest.light_grid.lai = np.zeros((nx, ny, nz), dtype=np.float32)
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
        forest, cfg.light, geom=cfg.geom,
        r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent,
        vigor_ref=cfg.sim.vigor_ref, vigor_diameter_gain=cfg.sim.vigor_diameter_gain,
    )
    _warn_if_buds_outside_grid(union_buds, light_grid)
    return perceive_light(
        union_buds, light_grid, cfg.light,
        seed=int(np.random.SeedSequence([cfg.seed, iteration]).generate_state(1)[0]),
    )


def _warn_if_buds_outside_grid(union_buds, light_grid) -> None:
    """One-time warning (#FIX G) when any active bud lies outside the light grid
    AABB during perception. A vigorous leader can grow past the sky margin and then
    read full sun (rays starting outside the grid accumulate no optical depth), so
    silent under-shading is otherwise invisible. Cheap: a single vectorized in-bounds
    test on the stacked positions; fires the logger.warning at most once per process."""
    global _OVERSHOOT_WARNED
    if _OVERSHOOT_WARNED or not union_buds:
        return
    pos = np.asarray([b.position for b in union_buds], dtype=np.float64)
    lo = light_grid.origin
    hi = light_grid.origin + light_grid.cell_size * np.array(light_grid.resolution)
    outside = np.any((pos < lo) | (pos >= hi), axis=1)
    n_out = int(outside.sum())
    if n_out:
        logger.warning(
            "%d/%d active bud(s) lie outside the light grid AABB during perception; "
            "they read full sun (no shading). The leader likely overshot the sky "
            "margin — consider raising the y-margin or light.grid_size.",
            n_out, len(union_buds),
        )
        _OVERSHOOT_WARNED = True


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


def _compute_quality(forest: Forest, union_buds, res, light_info, cfg: Config) -> tuple[dict, dict]:
    """Compute two parallel quality currencies and return ``(quality_light, quality_marker)``.

    Both start from the marker-perception count ``res.quality`` and both receive the
    per-axis bud-break bias. They differ ONLY in the light multiply:

    * ``quality_light`` = marker_count * light_factor * bud_break_bias — the
      light-weighted currency that drives vigor allocation (bh.allocate /
      compute_v_subtree), recorded qualities, and shedding.
    * ``quality_marker`` = marker_count * bud_break_bias (NO light_factor) — the
      marker-only currency whose units match the integer marker counts that
      ``sympodial.q_threshold`` is calibrated against. Used ONLY for the sympodial
      promotion decision (#FIX F); mixing the unitless light_factor into that
      threshold otherwise made it light-magnitude-dependent.

    Vigor and shedding stay light-weighted by design — leaving the shedding path
    light-weighted is an accepted, documented limitation (we do not refactor it here).
    """
    if light_info is not None:
        quality_light = {b: res.quality[b] * light_info.light_factor[b] for b in union_buds}
    else:
        quality_light = dict(res.quality)
    quality_marker = dict(res.quality)

    # Bud-break bias: modulate lateral quality by position along parent axis.
    # Applied identically to BOTH currencies. Skipped entirely in the default
    # (uniform / strength=0) case to avoid the per-tree axis walk when off.
    bb = cfg.sim.bud_break_bias
    if bb.mode != "uniform" and bb.strength > 0.0:
        for tree in forest.trees:
            positions = compute_axis_positions(tree)
            for b, (node_index, axis_length) in positions.items():
                w = position_weight(node_index, axis_length, bb.mode, bb.strength)
                if b in quality_light:
                    quality_light[b] = quality_light[b] * w
                if b in quality_marker:
                    quality_marker[b] = quality_marker[b] * w
    return quality_light, quality_marker


def _iteration_step(forest: Forest, cfg: Config, iteration: int, t: float, state: _SimState, t0: float, activity: float = 1.0) -> int:
    """One simulation step on the whole forest. Returns total nodes created.

    ``activity`` in (0, 1] is the graded seasonal multiplier (#65); it scales the
    emitted internode length so shoots taper near the window edges. Defaults to
    1.0 (full growth) so a mis-threaded call can never silently zero growth.

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

    quality, quality_marker = _compute_quality(forest, union_buds, res, light_info, cfg)

    new_node_positions: list[np.ndarray] = []
    nodes_created_this_step = 0
    for tree in forest.trees:
        created, positions = _grow_tree(
            tree, forest, cfg, iteration, t, state, res, light_info, quality,
            quality_marker, activity,
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
    res, light_info, quality: dict, quality_marker: dict, activity: float = 1.0,
) -> tuple[int, list[np.ndarray]]:
    """Grow one tree by one iteration. Returns (nodes_created, new_positions).

    Single bud-major pass (#20): each active bud computes its continuous BH flux
    v_b, updates its recent_vigor EMA, and — unless dormant / U-turning / blocked —
    emits exactly ONE internode whose length is the saturating shoot_extension(v_b).
    The internode records vigor=v_b. Perception (res) and light (light_info) are
    computed once per iteration upstream in _iteration_step, so no in-iteration
    re-perception is needed.
    """
    new_positions: list[np.ndarray] = []
    nodes_created = 0

    if cfg.sim.sympodial.enabled:
        # Currency separation (#FIX F): the sympodial threshold (sympodial.q_threshold)
        # is calibrated against integer marker counts, so feed it the marker-ONLY
        # quality (no light_factor multiply). Vigor allocation / v_subtree / shedding
        # below stay on the light-weighted ``quality`` by design.
        promote_lateral_if_failing(tree, quality_marker, cfg.sim.sympodial)
    v_subtree = compute_v_subtree(tree, quality)
    v_by_bud = allocate(
        tree, quality=quality,
        alpha=cfg.sim.alpha_basipetal, lambda_apical=cfg.sim.lambda_apical,
        v_subtree=v_subtree,
    )
    record_qualities(tree, v_subtree=v_subtree)

    s = cfg.sim.vigor_smoothing
    new_active: list[Bud] = []
    for bud in list(tree.active_buds):
        v_b = float(v_by_bud.get(bud, 0.0))
        # Hysteresis: smooth v_b, then threshold the EMA. A single starved/lucky
        # iteration cannot flip the bud's active/dormant state (#20).
        # Warmup note: recent_vigor starts at 0, so a bud's first evaluation only
        # reaches s*v_b — a marginal lateral can sit DORMANT one extra iteration
        # while its EMA climbs. This is intentional hysteresis, NOT a bug: dormant
        # buds are re-evaluated every iteration (they stay in new_active), so it is
        # a one-iteration lag, not a kill. Do not "fix" it by seeding recent_vigor
        # = v_b — that removes the lag the hysteresis is meant to provide.
        bud.recent_vigor = (1.0 - s) * bud.recent_vigor + s * v_b
        v_perc = res.direction[bud]
        v_perc_norm = float(np.linalg.norm(v_perc))
        if bud.recent_vigor < cfg.sim.vigor_dormancy or v_perc_norm < 1e-12:
            bud.state = BudState.DORMANT
            new_active.append(bud)
            continue

        light_grad = light_info.gradient[bud] if light_info else None
        is_main = (bud is bud.parent_node.terminal_bud)
        parent_iod = bud.parent_node.parent_internode
        branch_age_years = (t - parent_iod.birth_time) if parent_iod is not None else 0.0
        d = growth_direction(
            v_perception=res.direction[bud],
            current_direction=bud.direction,
            cfg=cfg.tropism,
            is_main_axis=is_main,
            light_gradient=light_grad,
            axis_order=bud.axis_order,
            branch_age_years=branch_age_years,
            spray_plane_normal=bud.spray_plane_normal,
        )
        # U-turn check on the blended growth direction (envelope-boundary curl).
        if float(np.dot(d, bud.direction)) < cfg.sim.cos_min_perception:
            bud.state = BudState.DORMANT
            new_active.append(bud)
            continue

        target = _internode_target(bud, v_b, cfg, iteration, t, state, activity)
        new_pos = bud.position + d * target

        if forest.obstacles:
            if segment_blocked(bud.position, new_pos, forest.obstacles):
                bud.state = BudState.DORMANT
                new_active.append(bud)
                continue
            if any_contains(new_pos, forest.obstacles):
                bud.state = BudState.DEAD
                continue

        new_node, terminal = _emit_node(
            bud, d, new_pos, target, v_b, is_main, light_info, tree, cfg, t, state
        )
        new_positions.append(new_pos)
        nodes_created += 1
        new_active.extend(new_node.lateral_buds)
        new_active.append(terminal)

    tree.active_buds = [b for b in new_active if b.state != BudState.DEAD]
    return nodes_created, new_positions


def _internode_target(cur: Bud, v_b: float, cfg: Config, iteration: int, t: float, state: _SimState, activity: float = 1.0) -> float:
    """Saturating shoot-extension length for the new internode, optionally jittered.

    The jitter RNG is salted by (seed, _ILEN_SALT, iteration, node_index) so the
    draw is reproducible and independent of perception/light ordering.

    ``activity`` in (0, 1] is the graded seasonal multiplier (#65), applied LAST —
    after the saturating curve and the jitter draw — so it scales the final
    emitted length without perturbing the vigor->length response or the RNG
    stream. At activity == 1.0 the multiply is the IEEE-exact identity, so default
    presets stay byte-identical."""
    base_length = shoot_extension(v_b, cfg.sim.shoot_extension_max, cfg.sim.vigor_ref)
    if cfg.sim.internode_length_jitter > 0:
        # iteration is the integer loop index, used only for RNG seeding (not biological time).
        ss = np.random.SeedSequence([cfg.seed, _ILEN_SALT, iteration, state.node_index])
        rng = np.random.default_rng(ss.generate_state(1)[0])
        factor = max(0.5, min(1.5, rng.normal(1.0, cfg.sim.internode_length_jitter)))
        base_length *= factor
    return base_length * activity


def _lateral_spray_normal(
    spray_on: bool, parent_axis_normal: np.ndarray | None, birth_direction: np.ndarray
) -> np.ndarray | None:
    """Spray-plane normal a NEW lateral axis carries (#55).

    Off => None (legacy). On => inherit the parent axis's normal when it has one
    (coherent multi-order frond: order-2+ fan in the order-1 plane), else derive a
    fresh one from the lateral's own birth direction (the case where the parent is
    the trunk / a normal-less axis). May still be None if the birth direction is
    near-vertical (no well-defined horizontal-ish plane)."""
    if not spray_on:
        return None
    if parent_axis_normal is not None:
        return parent_axis_normal
    return spray_plane_normal_from_direction(birth_direction)


def _emit_node(
    cur: Bud, d: np.ndarray, new_pos: np.ndarray, target: float, v_b: float, is_main: bool,
    light_info, tree: Tree, cfg: Config, t: float, state: _SimState,
) -> tuple[Node, Bud]:
    """Create the node + internode + terminal/lateral/reserve buds for one bud
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
        vigor=v_b,
    )
    cur.parent_node.children_internodes.append(iod)
    new_node.parent_internode = iod
    tree.all_internodes.append(iod)

    # Spray-plane normal (#55) of ``cur``'s axis: positions cur's laterals within
    # its frond plane and flattens them toward it. None when the feature is off
    # (cur.spray_plane_normal stays None) or cur is on a normal-less axis (trunk).
    spray_on = cfg.tropism.spray_plane_enabled
    axis_normal = cur.spray_plane_normal

    # The terminal continues ``cur``'s axis, so it carries the next phyllotactic
    # ordinal along that lineage — and the same spray-plane normal.
    terminal = Bud(
        position=new_pos.copy(), direction=d,
        axis_order=cur.axis_order, parent_node=new_node,
        low_quality_steps=cur.low_quality_steps,
        low_light_steps=cur.low_light_steps,
        axis_node_ordinal=cur.axis_node_ordinal + 1,
        spray_plane_normal=axis_normal,
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
        spray_plane_normal=axis_normal,
    )
    state.node_index += 1
    # Shade-avoidance at initiation (#63): in shade, a lateral breaks ACTIVE only
    # with probability p_break = lateral_break_probability(lf, strength); otherwise
    # it starts RESERVE (kept in dormant_reserve_buds, reactivatable via reiteration
    # when a shaded branch is later shed). ``lf`` is the EMITTING bud's light factor
    # — the new laterals have no light of their own until the next perception pass.
    # Disabled / strength 0 / full sun => p_break == 1.0: no RNG is drawn and every
    # lateral breaks ACTIVE, byte-identical to the legacy path. The draw is salted
    # by the global emission ordinal (state.node_index, unique per node) under a
    # private salt, so it never perturbs the phyllotaxy / internode-length streams.
    sa = cfg.sim.shade_avoidance
    p_break = (
        lateral_break_probability(lf, sa.strength)
        if (sa.enabled and light_info is not None) else 1.0
    )
    sa_rng = (
        np.random.default_rng(
            np.random.SeedSequence(
                [cfg.seed, _SHADE_SALT, state.node_index]
            ).generate_state(1)[0]
        )
        if p_break < 1.0 else None
    )
    # Laterals each begin a NEW axis → their phyllotactic ordinal restarts at 0
    # (the Bud default), so each branch axis advances divergence from its own base.
    for ld in lateral_dirs:
        lat = Bud(
            position=new_pos.copy(), direction=ld,
            axis_order=cur.axis_order + 1, parent_node=new_node,
            spray_plane_normal=_lateral_spray_normal(spray_on, axis_normal, ld),
        )
        if sa_rng is not None and sa_rng.random() >= p_break:
            lat.state = BudState.RESERVE
            new_node.dormant_reserve_buds.append(lat)
        else:
            new_node.lateral_buds.append(lat)

    # Phase 2B: emit RESERVE buds (not added to active_buds).
    if cfg.phyllotaxy.dormant_reserve_count > 0:
        reserve_dirs = reserve_bud_directions(
            d, cfg.phyllotaxy,
            node_index=axis_ord,
            seed=cfg.seed,
            count=cfg.phyllotaxy.dormant_reserve_count,
            axis_order=cur.axis_order,
            spray_plane_normal=axis_normal,
        )
        for rd in reserve_dirs:
            rbud = Bud(
                position=new_pos.copy(), direction=rd,
                axis_order=cur.axis_order + 1, parent_node=new_node,
                state=BudState.RESERVE,
                spray_plane_normal=_lateral_spray_normal(spray_on, axis_normal, rd),
            )
            new_node.dormant_reserve_buds.append(rbud)

    # Leaves (#14): emit leaf_cluster_count leaves at this node, using the
    # per-axis phyllotactic azimuth (same #24 ordinal that drives lateral buds).
    if cfg.geom.enable_leaves and cfg.geom.leaf_cluster_count > 0:
        for az in leaf_azimuths(
            cfg.phyllotaxy,
            node_index=axis_ord,
            axis_order=cur.axis_order,
            count=cfg.geom.leaf_cluster_count,
        ):
            new_node.leaves.append(
                Leaf(parent_node=new_node, azimuth=az, birth_time=t,
                     state=LeafState.ACTIVE)
            )

    cur.state = BudState.DEAD
    return new_node, terminal


def _apply_temporal_dynamics(forest: Forest, cfg: Config, t: float) -> None:
    """Per-iteration aging updates. Order matters: lengths first (sag reads
    load = length × diameter²), diameters next (sag reads diameter), sag last."""
    if cfg.sim.elongation.enabled:
        for tree in forest.trees:
            update_lengths(tree, current_time=t, cfg=cfg.sim.elongation)
    for tree in forest.trees:
        update_diameters_incremental(
            tree, r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent,
            vigor_ref=cfg.sim.vigor_ref, vigor_diameter_gain=cfg.sim.vigor_diameter_gain,
        )
    if cfg.sag.enabled:
        for tree in forest.trees:
            apply_sag(tree, cfg=cfg.sag)
    # Leaf caducity (#61): age/season -> LeafState. Independent of mesh geometry,
    # so order vs. sag is irrelevant; abscised leaves drop off the ACTIVE roster
    # and vanish from the rendered mesh via geom.leaves' existing filter.
    advance_leaf_states(forest, cfg, t)
