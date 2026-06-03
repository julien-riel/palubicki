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
    # Centered gradient (#FIX D): under open sky all T_k = 1 → zero gradient
    # (no spurious pull toward the light direction).
    np.testing.assert_allclose(res.gradient[bud], [0.0, 0.0, 0.0], atol=1e-9)


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


def test_perceive_light_no_seed_collision_across_iterations():
    """Same bud, two perceive_light calls with different 'seed' values must produce
       different sampling — even if the seeds differ by a small amount typical of
       iteration counters."""
    grid = _grid_uniform(2.0)
    bud = Bud(position=np.array([5.0, 5.0, 5.0]), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=Node(position=np.zeros(3)))
    cfg = LightConfig(n_rays=16, k_absorption=0.5)
    # Across iterations, the simulator passes seed = cfg_seed + iter.
    # With many buds, prior code used seed+i, which collides as i+1 vs (i+next_iter).
    # Test surrogate: two adjacent integer seeds should not produce identical results.
    res_a = perceive_light([bud], grid, cfg, seed=100)
    res_b = perceive_light([bud], grid, cfg, seed=101)
    # The two should be quite different — at minimum, the gradients should not be identical.
    assert not np.array_equal(res_a.gradient[bud], res_b.gradient[bud])


def test_perceive_light_deterministic():
    grid = _grid_uniform(1.0)
    bud = Bud(position=np.array([5.0, 5.0, 5.0]), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=Node(position=np.zeros(3)))
    cfg = LightConfig(n_rays=16, k_absorption=0.5)
    res1 = perceive_light([bud], grid, cfg, seed=42)
    res2 = perceive_light([bud], grid, cfg, seed=42)
    assert res1.light_factor[bud] == res2.light_factor[bud]
    np.testing.assert_array_equal(res1.gradient[bud], res2.gradient[bud])
