import math

import numpy as np
import pytest

from palubicki.config import load_config
from palubicki.sim.simulator import simulate_forest

pytestmark = pytest.mark.slow


def _angle_to_xy_plane_deg(direction: np.ndarray) -> float:
    """Angle (deg) between a unit vector and the horizontal plane.
    0 = horizontal, 90 = vertical."""
    d = direction / np.linalg.norm(direction)
    vertical_component = abs(float(d[1]))
    return math.degrees(math.asin(min(1.0, vertical_component)))


def _structural_depth(tree) -> dict:
    """BFS from root; returns {node_id: branch_depth}.

    branch_depth is the number of non-main-axis edges traversed to reach
    a node from the root.  Trunk nodes have depth 0, first-order laterals
    have depth 1, etc.  This is independent of ``axis_order`` (which gets
    reset by sympodial promotion) and correctly reflects topological branch
    order.
    """
    node_depth: dict[int, int] = {id(tree.root): 0}
    for iod in tree.all_internodes:
        parent_depth = node_depth.get(id(iod.parent_node))
        if parent_depth is None:
            continue
        child_depth = parent_depth if iod.is_main_axis else parent_depth + 1
        if id(iod.child_node) not in node_depth:
            node_depth[id(iod.child_node)] = child_depth
    return node_depth


def test_oak_laterals_tilt_toward_horizontal(tmp_path):
    cfg = load_config(
        yaml_path=None,
        cli_overrides={"sim.max_simulation_years": 30, "envelope.marker_count": 8000},
        output=tmp_path / "oak.glb",
        species="oak",
    )
    forest = simulate_forest(cfg)
    tree = forest.trees[0]

    node_depth = _structural_depth(tree)

    lateral_angles = []
    trunk_angles = []
    for iod in tree.all_internodes:
        depth = node_depth.get(id(iod.child_node))
        d = iod.child_node.position - iod.parent_node.position
        if np.linalg.norm(d) < 1e-9:
            continue
        if depth == 1:
            lateral_angles.append(_angle_to_xy_plane_deg(d))
        elif depth == 0:
            trunk_angles.append(_angle_to_xy_plane_deg(d))

    # The fix to co-located bud competition (#XX) lets the leader survive, so the
    # trunk now forms a real monopodial axis that sheds O(100s) of genuine
    # first-order laterals — versus ~10 quasi-random ones when leaders died.
    assert len(lateral_angles) >= 30, f"need >=30 first-order laterals, got {len(lateral_angles)}"
    assert len(trunk_angles) >= 5, f"need a trunk to compare against, got {len(trunk_angles)}"

    mean_lateral = float(np.mean(lateral_angles))
    mean_trunk = float(np.mean(trunk_angles))
    # Plagiotropism (w_plagiotropism_lateral=0.60 in oak.yaml) is a *differential*
    # pull: first-order laterals are bent toward the horizontal RELATIVE to the
    # near-vertical leader. An absolute "mean < 40deg" bound was an artifact of the
    # pre-fix 10-lateral sample; with a healthy trunk (~79deg) the true population
    # averages ~57deg — still clearly plagiotropic, since that is ~20deg more
    # horizontal than the leader. Assert that gap, not an absolute angle.
    assert mean_trunk - mean_lateral >= 12.0, (
        f"laterals should be markedly more horizontal than the trunk: "
        f"trunk={mean_trunk:.1f}deg, laterals={mean_lateral:.1f}deg"
    )
    # And a substantial fraction should be horizontal-leaning (below 45deg).
    frac_horizontal = float((np.asarray(lateral_angles) < 45.0).mean())
    assert frac_horizontal >= 0.15, (
        f"expected >=15% of first-order laterals below 45deg, got {100*frac_horizontal:.0f}%"
    )
