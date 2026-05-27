import math
from collections import deque

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
        cli_overrides={"sim.max_iterations": 30, "envelope.marker_count": 8000},
        output=tmp_path / "oak.glb",
        species="oak",
    )
    forest = simulate_forest(cfg)
    tree = forest.trees[0]

    node_depth = _structural_depth(tree)

    angles = []
    for iod in tree.all_internodes:
        if node_depth.get(id(iod.child_node)) != 1:
            continue
        d = iod.child_node.position - iod.parent_node.position
        if np.linalg.norm(d) < 1e-9:
            continue
        angles.append(_angle_to_xy_plane_deg(d))

    # At 30 iterations / 8000 markers the trunk generates O(10-20) first-order
    # laterals.  We require at least 5 to make the angle statistics meaningful.
    # (Observed: ~12 with default seed.)
    assert len(angles) >= 5, f"need >=5 first-order laterals, got {len(angles)}"
    mean_angle = float(np.mean(angles))
    median_angle = float(np.median(angles))
    # Plagiotropism (w_plagiotropism_lateral=0.60 in oak.yaml) should pull
    # first-order laterals toward the horizontal.  Thresholds are generous
    # enough to accommodate stochastic variation across random seeds:
    # observed mean ~29-35 deg, median ~28-31 deg.
    assert mean_angle < 40.0, f"mean tilt to XY should be <40deg, got {mean_angle:.1f}"
    assert median_angle < 35.0, f"median tilt to XY should be <35deg, got {median_angle:.1f}"
