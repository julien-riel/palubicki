# src/palubicki/sim/simulator.py
from __future__ import annotations

import logging
import time

import numpy as np

from palubicki.config import Config
from palubicki.sim.bh import allocate
from palubicki.sim.envelope import sample_markers
from palubicki.sim.light import LightGrid
from palubicki.sim.light_perception import perceive_light
from palubicki.sim.markers import MarkerCloud
from palubicki.sim.phyllotaxy import lateral_bud_directions
from palubicki.sim.shedding import record_qualities, shed_low_quality
from palubicki.sim.space_competition import perceive
from palubicki.sim.tree import Bud, BudState, Internode, Node, Tree
from palubicki.sim.tropisms import growth_direction

logger = logging.getLogger(__name__)


def simulate(cfg: Config) -> Tree:
    rng = np.random.default_rng(cfg.seed)
    marker_positions = sample_markers(cfg.envelope, rng)
    markers = MarkerCloud(marker_positions)

    root_pos = np.array([cfg.envelope.center[0], 0.0, cfg.envelope.center[2]], dtype=float)
    root = Node(position=root_pos)
    bud = Bud(
        position=root_pos.copy(),
        direction=np.array([0.0, 1.0, 0.0]),
        axis_order=0,
        parent_node=root,
    )
    root.terminal_bud = bud
    tree = Tree(root=root, active_buds=[bud])

    light_grid = LightGrid.from_config(cfg.light, cfg.envelope) if cfg.light.enabled else None

    node_index = 0
    no_new_streak = 0
    t0 = time.time()

    for iteration in range(cfg.sim.max_iterations):
        if not tree.active_buds:
            break

        if light_grid is not None:
            light_grid.rebuild_from_tree(
                tree, cfg.light,
                r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent,
            )
            light_info = perceive_light(
                tree.active_buds, light_grid, cfg.light,
                seed=int(np.random.SeedSequence([cfg.seed, iteration]).generate_state(1)[0]),
            )
        else:
            light_info = None

        res = perceive(
            tree.active_buds, markers,
            r_perception=cfg.sim.r_perception,
            theta_perception_deg=cfg.sim.theta_perception_deg,
        )

        if light_info is not None:
            quality = {b: res.quality[b] * light_info.light_factor[b] for b in tree.active_buds}
        else:
            quality = res.quality

        n_by_bud = allocate(
            tree, quality=quality,
            alpha=cfg.sim.alpha_basipetal, lambda_apical=cfg.sim.lambda_apical,
        )
        record_qualities(tree, quality=quality)

        new_node_positions: list[np.ndarray] = []
        new_active: list[Bud] = []
        nodes_created_this_step = 0

        for bud_old in list(tree.active_buds):
            n = n_by_bud.get(bud_old, 0)
            v_perc = res.direction[bud_old]
            if n < 1 or np.linalg.norm(v_perc) < 1e-12:
                bud_old.state = BudState.DORMANT
                new_active.append(bud_old)
                continue

            current_bud = bud_old
            for step in range(n):
                light_grad = light_info.gradient[current_bud] if light_info else None
                d = growth_direction(
                    v_perception=res.direction[current_bud],
                    current_direction=current_bud.direction,
                    cfg=cfg.tropism,
                    light_gradient=light_grad,
                )
                new_pos = current_bud.position + d * cfg.sim.internode_length
                new_node = Node(position=new_pos)
                iod = Internode(
                    parent_node=current_bud.parent_node,
                    child_node=new_node,
                    length=cfg.sim.internode_length,
                    is_main_axis=(current_bud is current_bud.parent_node.terminal_bud),
                    window=cfg.shedding.window,
                )
                current_bud.parent_node.children_internodes.append(iod)
                new_node.parent_internode = iod
                tree.all_internodes.append(iod)
                new_node_positions.append(new_pos)
                nodes_created_this_step += 1

                terminal = Bud(
                    position=new_pos.copy(), direction=d,
                    axis_order=current_bud.axis_order, parent_node=new_node,
                )
                new_node.terminal_bud = terminal

                lateral_dirs = lateral_bud_directions(d, cfg.phyllotaxy, node_index=node_index)
                node_index += 1
                for ld in lateral_dirs:
                    lat = Bud(
                        position=new_pos.copy(), direction=ld,
                        axis_order=current_bud.axis_order + 1, parent_node=new_node,
                    )
                    new_node.lateral_buds.append(lat)

                new_active.extend(new_node.lateral_buds)
                current_bud.state = BudState.DEAD
                if step + 1 < n:
                    if cfg.sim.re_perceive_per_substep:
                        sub_result = perceive(
                            [terminal], markers,
                            r_perception=cfg.sim.r_perception,
                            theta_perception_deg=cfg.sim.theta_perception_deg,
                        )
                        res.direction[terminal] = sub_result.direction[terminal]
                        res.quality[terminal] = sub_result.quality[terminal]
                        if light_grid is not None and light_info is not None:
                            lf, grad = light_grid.sample_hemisphere(
                                terminal.position,
                                n_rays=cfg.light.n_rays,
                                light_direction=np.asarray(cfg.light.light_direction, dtype=np.float64),
                                k=cfg.light.k_absorption,
                                    seed=int(np.random.SeedSequence([cfg.seed, iteration, step + 1]).generate_state(1)[0]),
                            )
                            light_info.light_factor[terminal] = lf
                            light_info.gradient[terminal] = grad
                        if np.linalg.norm(res.direction[terminal]) < 1e-12:
                            terminal.state = BudState.DORMANT
                            new_active.append(terminal)
                            break
                    else:
                        # Cheap approximation: reuse the original bud's perception.
                        res.direction[terminal] = res.direction.get(current_bud, np.zeros(3))
                        res.quality[terminal] = res.quality.get(current_bud, 0)
                        if light_info is not None:
                            light_info.light_factor[terminal] = light_info.light_factor.get(current_bud, 1.0)
                            light_info.gradient[terminal] = light_info.gradient.get(current_bud, np.zeros(3))
                    current_bud = terminal
                else:
                    new_active.append(terminal)

        tree.active_buds = [b for b in new_active if b.state != BudState.DEAD]

        if new_node_positions:
            markers.kill_near(np.array(new_node_positions), cfg.sim.r_kill)

        shed_low_quality(tree, cfg=cfg.shedding)

        if nodes_created_this_step == 0:
            no_new_streak += 1
        else:
            no_new_streak = 0
        if no_new_streak >= 2:
            break

        logger.info(
            "[%.1fs] sim/iter %d/%d  buds=%d active=%d  internodes=%d",
            time.time() - t0,
            iteration + 1, cfg.sim.max_iterations,
            len(tree.active_buds),
            sum(1 for b in tree.active_buds if b.state == BudState.ACTIVE),
            len(tree.all_internodes),
        )

    return tree
