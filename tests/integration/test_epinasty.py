import math

import numpy as np
import pytest

from palubicki.config import load_config
from palubicki.sim.simulator import simulate_forest

pytestmark = pytest.mark.slow


def _angle_to_xy_plane_deg(direction: np.ndarray) -> float:
    """Angle (deg) to the horizontal plane. 0 = horizontal, 90 = vertical."""
    d = direction / np.linalg.norm(direction)
    return math.degrees(math.asin(min(1.0, abs(float(d[1])))))


def _structural_depth(tree) -> dict:
    """BFS from root; returns {node_id: branch_depth}.

    branch_depth counts non-main-axis edges from the root: trunk nodes are 0,
    first-order laterals 1, etc. Independent of ``axis_order`` (which sympodial
    promotion resets), so it reflects true topological branch order.
    """
    node_depth = {id(tree.root): 0}
    for iod in tree.all_internodes:
        parent_depth = node_depth.get(id(iod.parent_node))
        if parent_depth is None:
            continue
        child_depth = parent_depth if iod.is_main_axis else parent_depth + 1
        if id(iod.child_node) not in node_depth:
            node_depth[id(iod.child_node)] = child_depth
    return node_depth


def _grow_oak(tmp_path, *, epinasty: bool):
    overrides = {"sim.max_simulation_years": 30, "envelope.marker_count": 8000}
    # OFF path relies on TropismConfig.epinasty_enabled defaulting to False.
    if epinasty:
        overrides["tropism.epinasty_enabled"] = True
        overrides["tropism.epinasty_tau_years"] = 8.0
    cfg = load_config(
        yaml_path=None, cli_overrides=overrides,
        output=tmp_path / "oak.glb", species="oak",
    )
    return simulate_forest(cfg).trees[0]


def _first_order_angles(tree):
    node_depth = _structural_depth(tree)
    angles = []
    for iod in tree.all_internodes:
        if node_depth.get(id(iod.child_node)) != 1:
            continue
        d = iod.child_node.position - iod.parent_node.position
        if np.linalg.norm(d) < 1e-9:
            continue
        angles.append(_angle_to_xy_plane_deg(d))
    return angles


def test_epinasty_keeps_first_order_laterals_steeper_than_full_plagiotropism(tmp_path):
    """Epinasty ON: laterals on young wood never fully horizontalize, so the
    population is steeper (more vertical) on average than the epinasty-OFF run
    where full plagiotropism applies from node one."""
    off = _first_order_angles(_grow_oak(tmp_path, epinasty=False))
    on = _first_order_angles(_grow_oak(tmp_path, epinasty=True))

    assert len(off) >= 30 and len(on) >= 30, (
        f"need a healthy first-order population: off={len(off)}, on={len(on)}"
    )
    mean_off = float(np.mean(off))
    mean_on = float(np.mean(on))
    # angle-to-horizontal: larger = steeper/more vertical
    assert mean_on > mean_off + 3.0, (
        f"epinasty should keep laterals steeper on average: "
        f"on={mean_on:.1f}deg vs off={mean_off:.1f}deg"
    )


def test_epinasty_young_wood_steeper_than_old_wood(tmp_path):
    """Within the epinasty-ON tree, first-order laterals on YOUNG wood are
    steeper than those on OLD wood."""
    tree = _grow_oak(tmp_path, epinasty=True)
    node_depth = _structural_depth(tree)
    t_end = max((iod.birth_time for iod in tree.all_internodes), default=0.0)

    young, old = [], []
    for iod in tree.all_internodes:
        if node_depth.get(id(iod.child_node)) != 1:
            continue
        d = iod.child_node.position - iod.parent_node.position
        if np.linalg.norm(d) < 1e-9:
            continue
        parent = iod.parent_node.parent_internode
        if parent is None:
            continue
        age = t_end - parent.birth_time
        ang = _angle_to_xy_plane_deg(d)
        # tau=8 -> ramp ~0.63 at age=tau (still steep); 2*tau=16 -> ~0.86 (arched).
        if age <= 8.0:
            young.append(ang)
        elif age >= 16.0:
            old.append(ang)

    assert len(young) >= 5 and len(old) >= 5, (
        f"need both cohorts: young={len(young)}, old={len(old)}"
    )
    assert float(np.mean(young)) > float(np.mean(old)) + 3.0, (
        f"young-wood laterals should be steeper than old-wood: "
        f"young={np.mean(young):.1f}deg, old={np.mean(old):.1f}deg"
    )
