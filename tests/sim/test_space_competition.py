# tests/sim/test_space_competition.py
import numpy as np

from palubicki.sim.markers import MarkerCloud
from palubicki.sim.space_competition import PerceptionResult, perceive
from palubicki.sim.tree import Bud, Node


def _make_bud(pos, direction, parent=None):
    parent = parent or Node(position=np.asarray(pos, dtype=float))
    return Bud(position=np.asarray(pos, dtype=float),
               direction=np.asarray(direction, dtype=float) / np.linalg.norm(direction),
               axis_order=0, parent_node=parent)


def test_marker_in_front_is_perceived():
    cloud = MarkerCloud(np.array([[0, 1, 0]], dtype=float))
    bud = _make_bud((0, 0, 0), (0, 1, 0))
    res: PerceptionResult = perceive([bud], cloud, r_perception=2.0, theta_perception_deg=60.0)
    assert res.quality[bud] == 1
    np.testing.assert_allclose(res.direction[bud], [0, 1, 0], atol=1e-7)


def test_marker_behind_not_perceived():
    cloud = MarkerCloud(np.array([[0, -1, 0]], dtype=float))
    bud = _make_bud((0, 0, 0), (0, 1, 0))
    res = perceive([bud], cloud, r_perception=2.0, theta_perception_deg=60.0)
    assert res.quality[bud] == 0


def test_marker_outside_cone_not_perceived():
    cloud = MarkerCloud(np.array([[1, 0.1, 0]], dtype=float))
    bud = _make_bud((0, 0, 0), (0, 1, 0))
    res = perceive([bud], cloud, r_perception=2.0, theta_perception_deg=30.0)
    assert res.quality[bud] == 0


def test_closest_bud_competition_unique_attribution():
    cloud = MarkerCloud(np.array([[0, 1, 0]], dtype=float))
    bud_close = _make_bud((0, 0.5, 0), (0, 1, 0))
    bud_far = _make_bud((0, -0.5, 0), (0, 1, 0))
    res = perceive([bud_close, bud_far], cloud, r_perception=5.0, theta_perception_deg=90.0)
    assert res.quality[bud_close] == 1
    assert res.quality[bud_far] == 0


def test_direction_normalized_or_zero():
    cloud = MarkerCloud(np.zeros((0, 3), dtype=float))
    bud = _make_bud((0, 0, 0), (0, 1, 0))
    res = perceive([bud], cloud, r_perception=1.0, theta_perception_deg=90.0)
    assert res.quality[bud] == 0
    np.testing.assert_allclose(res.direction[bud], [0, 0, 0])


def test_symmetric_markers_average_to_bud_direction():
    cloud = MarkerCloud(np.array([[0.5, 1, 0], [-0.5, 1, 0]], dtype=float))
    bud = _make_bud((0, 0, 0), (0, 1, 0))
    res = perceive([bud], cloud, r_perception=5.0, theta_perception_deg=90.0)
    assert res.quality[bud] == 2
    np.testing.assert_allclose(res.direction[bud], [0, 1, 0], atol=1e-7)


def test_colocated_buds_split_contested_marker_by_cone_alignment():
    """Terminal and lateral emitted at the SAME node share a position, so the
    distance key cannot separate them. A marker straight ahead of the terminal
    must go to the terminal (best cone alignment), and a marker along the lateral
    must go to the lateral — not be decided by bud-list index order.

    Bud order mirrors the real simulator: laterals are appended BEFORE the
    terminal, so the buggy index tiebreak would hand both markers to the lateral.
    """
    import math

    branch = math.radians(75.0)  # lateral inclined 75deg off the vertical axis
    lateral_dir = (math.sin(branch), 0.0, math.cos(branch))
    terminal_dir = (0.0, 0.0, 1.0)

    node = Node(position=np.zeros(3))
    lateral = _make_bud((0, 0, 0), lateral_dir, parent=node)
    terminal = _make_bud((0, 0, 0), terminal_dir, parent=node)

    # Marker straight up (aligned with terminal); marker along the lateral.
    up_marker = [0.0, 0.0, 1.0]
    side_marker = [math.sin(branch), 0.0, math.cos(branch)]
    cloud = MarkerCloud(np.array([up_marker, side_marker], dtype=float))

    res = perceive([lateral, terminal], cloud, r_perception=5.0, theta_perception_deg=90.0)

    assert res.quality[terminal] == 1
    assert res.quality[lateral] == 1
    np.testing.assert_allclose(res.direction[terminal], terminal_dir, atol=1e-7)
    np.testing.assert_allclose(res.direction[lateral], lateral_dir, atol=1e-7)


def test_empty_bud_list_returns_empty_result():
    """perceive() with no buds hits the early-return branch and returns empty dicts."""
    cloud = MarkerCloud(np.array([[0, 1, 0]], dtype=float))
    res = perceive([], cloud, r_perception=2.0, theta_perception_deg=60.0)
    assert res.quality == {}
    assert res.direction == {}
