import numpy as np
import pytest

from palubicki.config import ObstacleAABB
from palubicki.sim.obstacles import AABBObstacle


def test_aabb_contains_center():
    cfg = ObstacleAABB(min=(0.0, 0.0, 0.0), max=(2.0, 2.0, 2.0))
    o = AABBObstacle(cfg)
    pts = np.array([[1.0, 1.0, 1.0], [3.0, 0.0, 0.0], [0.0, 1.0, 1.0]])
    out = o.contains(pts)
    assert out.tolist() == [True, False, True]   # boundary inclusive


def test_aabb_contains_empty_array():
    o = AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)))
    out = o.contains(np.zeros((0, 3)))
    assert out.shape == (0,)


def test_aabb_segment_intersects_traverse():
    o = AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)))
    # Segment from outside left to outside right, through the box
    assert o.segment_intersects(np.array([-1.0, 0.5, 0.5]), np.array([2.0, 0.5, 0.5])) is True


def test_aabb_segment_intersects_start_inside():
    o = AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)))
    assert o.segment_intersects(np.array([0.5, 0.5, 0.5]), np.array([2.0, 0.5, 0.5])) is True


def test_aabb_segment_intersects_end_inside():
    o = AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)))
    assert o.segment_intersects(np.array([-1.0, 0.5, 0.5]), np.array([0.5, 0.5, 0.5])) is True


def test_aabb_segment_intersects_miss():
    o = AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)))
    assert o.segment_intersects(np.array([2.0, 2.0, 2.0]), np.array([3.0, 2.0, 2.0])) is False


def test_aabb_segment_short_segment_below_box():
    o = AABBObstacle(ObstacleAABB(min=(0, 1, 0), max=(1, 2, 1)))
    # Segment goes left-to-right at y=0.5, never reaches y=1
    assert o.segment_intersects(np.array([-1.0, 0.5, 0.5]), np.array([2.0, 0.5, 0.5])) is False


def test_aabb_aabb_returns_min_max():
    o = AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 2, 3)))
    amin, amax = o.aabb()
    assert tuple(amin) == (0.0, 0.0, 0.0)
    assert tuple(amax) == (1.0, 2.0, 3.0)


from palubicki.config import ObstacleSphere
from palubicki.sim.obstacles import SphereObstacle


def test_sphere_contains():
    o = SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=1.0))
    pts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.1, 0.0, 0.0], [-0.5, 0.5, 0.5]])
    out = o.contains(pts)
    assert out.tolist() == [True, True, False, True]


def test_sphere_segment_traverse():
    o = SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=1.0))
    assert o.segment_intersects(np.array([-2.0, 0.0, 0.0]), np.array([2.0, 0.0, 0.0])) is True


def test_sphere_segment_endpoint_inside():
    o = SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=1.0))
    assert o.segment_intersects(np.array([2.0, 0.0, 0.0]), np.array([0.5, 0.0, 0.0])) is True


def test_sphere_segment_miss():
    o = SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=1.0))
    assert o.segment_intersects(np.array([2.0, 2.0, 0.0]), np.array([3.0, 2.0, 0.0])) is False


def test_sphere_aabb():
    o = SphereObstacle(ObstacleSphere(center=(5.0, 1.0, -2.0), radius=2.0))
    amin, amax = o.aabb()
    assert tuple(amin) == (3.0, -1.0, -4.0)
    assert tuple(amax) == (7.0, 3.0, 0.0)
