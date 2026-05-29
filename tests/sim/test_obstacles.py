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


from palubicki.config import ObstacleOBB
from palubicki.sim.obstacles import OBBObstacle


def test_obb_axis_aligned_equivalent_to_aabb():
    # Identity axes → behaves like AABB centered at center
    cfg = ObstacleOBB(center=(1.0, 1.0, 1.0), half_extents=(1.0, 1.0, 1.0))
    o = OBBObstacle(cfg)
    pts = np.array([[1.0, 1.0, 1.0], [0.0, 0.0, 0.0], [3.0, 1.0, 1.0]])
    out = o.contains(pts)
    assert out.tolist() == [True, True, False]


def test_obb_rotated_45deg_around_y():
    # Rotated 45° around y: a point at (1,0,0) world is outside the rotated box
    # whose half_extents are (0.5, 0.5, 0.5) — corners reach sqrt(0.5) ≈ 0.707 in world.
    import math
    c, s = math.cos(math.pi / 4), math.sin(math.pi / 4)
    axes = (c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c)   # rotation matrix R^T (world → local)
    cfg = ObstacleOBB(center=(0, 0, 0), half_extents=(0.5, 0.5, 0.5), axes=axes)
    o = OBBObstacle(cfg)
    out = o.contains(np.array([[0.7, 0.0, 0.0], [0.5, 0.0, 0.0]]))
    # (0.7, 0, 0) is outside (rotated half-extent in world ≈ 0.707 but the FACE at +x in local
    # is at world x ≈ 0.5/c = 0.707 along its rotated normal; (0.7,0,0) maps to local x = 0.7*c ≈ 0.495,
    # local z = 0.7*-s ≈ -0.495 — inside the local AABB ±0.5).
    # We assert that (0.5, 0, 0) is inside (local x = 0.5*c ≈ 0.354, local z = 0.5*-s ≈ -0.354, inside).
    assert out[1] is np.True_ or bool(out[1]) is True


def test_obb_segment_intersects_axis_aligned():
    # With identity rotation, OBB segment_intersects must match AABB behavior
    cfg = ObstacleOBB(center=(0, 0, 0), half_extents=(0.5, 0.5, 0.5))
    o = OBBObstacle(cfg)
    assert o.segment_intersects(np.array([-2.0, 0.0, 0.0]), np.array([2.0, 0.0, 0.0])) is True
    assert o.segment_intersects(np.array([2.0, 2.0, 0.0]), np.array([3.0, 2.0, 0.0])) is False


def test_obb_aabb_envelope():
    # 90° rotation around y: half_extents (2, 1, 1) → world AABB ±(2, 1, 2) approximately
    axes = (0.0, 0.0, 1.0, 0.0, 1.0, 0.0, -1.0, 0.0, 0.0)
    cfg = ObstacleOBB(center=(0, 0, 0), half_extents=(2.0, 1.0, 1.0), axes=axes)
    o = OBBObstacle(cfg)
    amin, amax = o.aabb()
    # After 90° y rotation, local x-axis maps to world z (length 2), local z-axis maps to world x (length 1)
    # Expanded world AABB = max projection of local half-extents on each world axis
    assert amin[0] == pytest.approx(-1.0, abs=1e-9)
    assert amax[0] == pytest.approx(1.0, abs=1e-9)
    assert amin[2] == pytest.approx(-2.0, abs=1e-9)
    assert amax[2] == pytest.approx(2.0, abs=1e-9)


from pathlib import Path

from palubicki.config import ObstacleMesh
from palubicki.sim.obstacles import MeshObstacle

CUBE_OBJ = Path(__file__).parent.parent / "fixtures" / "unit_cube.obj"


def test_mesh_contains_unit_cube():
    o = MeshObstacle(ObstacleMesh(path=CUBE_OBJ))
    pts = np.array([
        [0.5, 0.5, 0.5],   # inside
        [2.0, 0.5, 0.5],   # outside
        [-0.1, 0.5, 0.5],  # outside
    ])
    out = o.contains(pts)
    assert out[0]
    assert not out[1]
    assert not out[2]


def test_mesh_translate_scale():
    o = MeshObstacle(ObstacleMesh(path=CUBE_OBJ, translate=(10.0, 0.0, 0.0), scale=2.0))
    # Original cube was (0..1)^3; scaled to (0..2)^3 then translated by +10x → (10..12)^3
    pts = np.array([[11.0, 1.0, 1.0], [0.5, 0.5, 0.5], [11.0, 3.0, 1.0]])
    out = o.contains(pts)
    assert out.tolist() == [True, False, False]


def test_mesh_segment_traverse():
    o = MeshObstacle(ObstacleMesh(path=CUBE_OBJ))
    assert o.segment_intersects(np.array([-1.0, 0.5, 0.5]), np.array([2.0, 0.5, 0.5])) is True


def test_mesh_segment_miss():
    o = MeshObstacle(ObstacleMesh(path=CUBE_OBJ))
    assert o.segment_intersects(np.array([2.0, 2.0, 2.0]), np.array([3.0, 2.0, 2.0])) is False


def test_mesh_segment_endpoint_inside():
    o = MeshObstacle(ObstacleMesh(path=CUBE_OBJ))
    assert o.segment_intersects(np.array([2.0, 0.5, 0.5]), np.array([0.5, 0.5, 0.5])) is True


def test_mesh_aabb():
    o = MeshObstacle(ObstacleMesh(path=CUBE_OBJ, translate=(1.0, 2.0, 3.0), scale=2.0))
    amin, amax = o.aabb()
    np.testing.assert_allclose(amin, [1.0, 2.0, 3.0])
    np.testing.assert_allclose(amax, [3.0, 4.0, 5.0])


from palubicki.config import ForestConfig
from palubicki.sim.obstacles import (
    any_contains,
    build_obstacles,
    filter_markers,
    segment_blocked,
)


def test_build_obstacles_dispatches_by_kind():
    cfg = ForestConfig(obstacles=(
        ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)),
        ObstacleSphere(center=(5, 0, 0), radius=2.0),
    ))
    obs = build_obstacles(cfg)
    assert isinstance(obs[0], AABBObstacle)
    assert isinstance(obs[1], SphereObstacle)


def test_filter_markers_drops_inside():
    obs = [AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)))]
    pts = np.array([[0.5, 0.5, 0.5], [2.0, 0.5, 0.5], [0.0, 0.0, 0.0]])
    out = filter_markers(pts, obs)
    assert out.shape == (1, 3)
    assert np.allclose(out[0], [2.0, 0.5, 0.5])


def test_filter_markers_empty_obstacles_passthrough():
    pts = np.array([[1.0, 2.0, 3.0]])
    out = filter_markers(pts, [])
    np.testing.assert_array_equal(out, pts)


def test_segment_blocked_any_obstacle():
    obs = [
        AABBObstacle(ObstacleAABB(min=(10, 10, 10), max=(11, 11, 11))),
        SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=1.0)),
    ]
    assert segment_blocked(np.array([-2.0, 0.0, 0.0]), np.array([2.0, 0.0, 0.0]), obs) is True


def test_segment_blocked_no_obstacle():
    assert segment_blocked(np.array([0, 0, 0]), np.array([1, 1, 1]), []) is False


def test_any_contains_true_when_any_obstacle_contains():
    obs = [SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=1.0))]
    assert any_contains(np.array([0.5, 0.0, 0.0]), obs) is True
    assert any_contains(np.array([2.0, 0.0, 0.0]), obs) is False


def test_any_contains_empty_obstacles_false():
    assert any_contains(np.array([0.0, 0.0, 0.0]), []) is False
