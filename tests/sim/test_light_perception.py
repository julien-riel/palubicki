import numpy as np
import pytest

from palubicki.config import EnvelopeConfig, LightConfig
from palubicki.sim.light import LightGrid
from palubicki.sim.light_perception import LightPerception, perceive_light
from palubicki.sim.tree import Bud, Node


def _grid_uniform(L: float) -> LightGrid:
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    grid.lai.fill(L)
    return grid


def test_perceive_light_open_sky():
    grid = _grid_uniform(0.0)
    bud = Bud(position=np.array([5.0, 5.0, 5.0]), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=Node(position=np.zeros(3)))
    cfg = LightConfig(n_rays=16, k_absorption=0.5)
    res = perceive_light([bud], grid, cfg, seed=42)
    assert isinstance(res, LightPerception)
    assert res.light_factor[bud] == pytest.approx(1.0, rel=1e-4)
    np.testing.assert_allclose(res.gradient[bud], [0.0, 1.0, 0.0], atol=0.2)


def test_perceive_light_dense_attenuation():
    grid = _grid_uniform(2.0)
    bud = Bud(position=np.array([5.0, 0.5, 5.0]), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=Node(position=np.zeros(3)))
    cfg = LightConfig(n_rays=16, k_absorption=0.5)
    res = perceive_light([bud], grid, cfg, seed=42)
    assert 0.0 < res.light_factor[bud] < 1.0


def test_perceive_light_empty_bud_list():
    grid = _grid_uniform(0.0)
    cfg = LightConfig(n_rays=16, k_absorption=0.5)
    res = perceive_light([], grid, cfg, seed=42)
    assert res.light_factor == {}
    assert res.gradient == {}


def test_perceive_light_deterministic():
    grid = _grid_uniform(1.0)
    bud = Bud(position=np.array([5.0, 5.0, 5.0]), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=Node(position=np.zeros(3)))
    cfg = LightConfig(n_rays=16, k_absorption=0.5)
    res1 = perceive_light([bud], grid, cfg, seed=42)
    res2 = perceive_light([bud], grid, cfg, seed=42)
    assert res1.light_factor[bud] == res2.light_factor[bud]
    np.testing.assert_array_equal(res1.gradient[bud], res2.gradient[bud])
