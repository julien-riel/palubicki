import numpy as np
import pytest

from palubicki.config import EnvelopeConfig, LightConfig
from palubicki.sim.light import LightGrid


def test_light_grid_explicit_bounds():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    env = EnvelopeConfig()
    grid = LightGrid.from_config(cfg, env)
    np.testing.assert_array_equal(grid.origin, np.array([0.0, 0.0, 0.0]))
    np.testing.assert_array_equal(grid.cell_size, np.array([1.0, 1.0, 1.0]))
    assert grid.resolution == (10, 10, 10)
    assert grid.lai.shape == (10, 10, 10)
    assert grid.lai.dtype == np.float32


def test_world_to_cell_basic():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    assert grid.world_to_cell(np.array([0.5, 0.5, 0.5])) == (0, 0, 0)
    assert grid.world_to_cell(np.array([5.5, 7.2, 1.1])) == (5, 7, 1)
    assert grid.world_to_cell(np.array([9.999, 9.999, 9.999])) == (9, 9, 9)


def test_world_to_cell_out_of_bounds_returns_none():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    assert grid.world_to_cell(np.array([-0.1, 0.0, 0.0])) is None
    assert grid.world_to_cell(np.array([10.1, 0.0, 0.0])) is None
    assert grid.world_to_cell(np.array([0.0, -1.0, 0.0])) is None


def test_cell_to_world_center():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    np.testing.assert_allclose(grid.cell_to_world_center(0, 0, 0), [0.5, 0.5, 0.5])
    np.testing.assert_allclose(grid.cell_to_world_center(5, 7, 1), [5.5, 7.5, 1.5])


def test_from_config_autofit_ellipsoid():
    """When origin/size are None, fit to envelope AABB with sky margin.
       AABB: [-2,2] × [-3,3] × [-2,2] → extent (4, 6, 4)
       origin = aabb_min - 0.1 * extent = (-2.4, -3.6, -2.4)
       size = (1.2*4, 1.4*6, 1.2*4) = (4.8, 8.4, 4.8)"""
    cfg = LightConfig(grid_origin=None, grid_size=None, grid_resolution=(16, 16, 16))
    env = EnvelopeConfig(shape="ellipsoid", rx=2.0, ry=3.0, rz=2.0, center=(0.0, 0.0, 0.0))
    grid = LightGrid.from_config(cfg, env)
    np.testing.assert_allclose(grid.origin, [-2.4, -3.6, -2.4], atol=1e-9)
    np.testing.assert_allclose(grid.cell_size * np.array(cfg.grid_resolution), [4.8, 8.4, 4.8], atol=1e-9)


def test_from_config_autofit_half_ellipsoid_starts_at_y_zero():
    cfg = LightConfig(grid_origin=None, grid_size=None, grid_resolution=(16, 16, 16))
    env = EnvelopeConfig(shape="half_ellipsoid", rx=2.0, ry=3.0, rz=2.0, center=(0.0, 0.0, 0.0))
    grid = LightGrid.from_config(cfg, env)
    # AABB y range [0, 3] → extent_y = 3 → origin.y = 0 - 0.1 * 3 = -0.3
    np.testing.assert_allclose(grid.origin[1], -0.3, atol=1e-9)


def test_from_config_autofit_cone():
    cfg = LightConfig(grid_origin=None, grid_size=None, grid_resolution=(16, 16, 16))
    env = EnvelopeConfig(shape="cone", rx=1.5, ry=8.0, rz=1.5, center=(0.0, 0.0, 0.0))
    grid = LightGrid.from_config(cfg, env)
    # Cone AABB: x/z in [-rx, rx]=[-1.5,1.5], y in [0, ry]=[0, 8]. extent=(3, 8, 3).
    # origin = aabb_min - 0.1 * extent = (-1.5 - 0.3, 0 - 0.8, -1.5 - 0.3) = (-1.8, -0.8, -1.8)
    np.testing.assert_allclose(grid.origin, [-1.8, -0.8, -1.8], atol=1e-9)
