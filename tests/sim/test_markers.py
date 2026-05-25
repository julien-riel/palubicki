# tests/sim/test_markers.py
import numpy as np

from palubicki.sim.markers import MarkerCloud


def test_init_all_alive():
    pts = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=float)
    cloud = MarkerCloud(pts)
    assert cloud.alive_count == 3


def test_query_radius_returns_alive_only():
    pts = np.array([[0, 0, 0], [0.5, 0, 0], [10, 0, 0]], dtype=float)
    cloud = MarkerCloud(pts)
    idx = cloud.query_radius(np.array([0.0, 0.0, 0.0]), 1.0)
    assert set(idx.tolist()) == {0, 1}


def test_kill_near_removes_and_rebuilds():
    pts = np.array([[0, 0, 0], [0.05, 0, 0], [5, 0, 0]], dtype=float)
    cloud = MarkerCloud(pts)
    cloud.kill_near(np.array([[0.0, 0.0, 0.0]]), kill_radius=0.1)
    assert cloud.alive_count == 1
    idx = cloud.query_radius(np.array([0.0, 0.0, 0.0]), 1.0)
    assert idx.tolist() == []


def test_alive_positions_returns_only_alive():
    pts = np.array([[0, 0, 0], [1, 0, 0]], dtype=float)
    cloud = MarkerCloud(pts)
    cloud.kill_near(np.array([[0.0, 0.0, 0.0]]), kill_radius=0.5)
    alive = cloud.alive_positions()
    np.testing.assert_array_equal(alive, np.array([[1, 0, 0]], dtype=float))
