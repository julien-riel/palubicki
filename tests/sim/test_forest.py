from pathlib import Path

import numpy as np
import pytest

from palubicki.config import (
    Config, EnvelopeConfig, ForestSeed, GeomConfig, LightConfig, PhyllotaxyConfig,
    SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.sim.forest import per_tree_config


def _base_cfg(**overrides) -> Config:
    return Config(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0),
        sim=SimConfig(), tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=Path("/tmp/x.glb"), seed=7,
        **overrides,
    )


def test_per_tree_config_translates_envelope():
    cfg = _base_cfg()
    seed = ForestSeed(position=(5.0, 0.0, 5.0))
    out = per_tree_config(cfg, seed, tree_index=0)
    assert out.envelope.center == (5.0, 0.0, 5.0)
    assert out.envelope.rx == 2.0   # other envelope fields preserved


def test_per_tree_config_applies_dotted_overrides():
    cfg = _base_cfg()
    seed = ForestSeed(
        position=(0.0, 0.0, 0.0),
        overrides={"envelope.shape": "cone", "tropism.w_gravity": 0.5},
    )
    out = per_tree_config(cfg, seed, tree_index=0)
    assert out.envelope.shape == "cone"
    assert out.tropism.w_gravity == 0.5


def test_per_tree_config_seed_derivation():
    cfg = _base_cfg()
    s_none = ForestSeed(position=(0.0, 0.0, 0.0))
    s_explicit = ForestSeed(position=(0.0, 0.0, 0.0), seed=99)
    assert per_tree_config(cfg, s_none, tree_index=3).seed == 7 + 3
    assert per_tree_config(cfg, s_explicit, tree_index=3).seed == 99


def test_per_tree_config_does_not_mutate_input():
    cfg = _base_cfg()
    seed = ForestSeed(position=(1.0, 0.0, 1.0), overrides={"sim.r_perception": 0.9})
    _ = per_tree_config(cfg, seed, tree_index=0)
    assert cfg.envelope.center == (0.0, 0.0, 0.0)   # original untouched
    assert cfg.sim.r_perception == 0.6


from palubicki.config import ObstacleAABB
from palubicki.sim.forest import forest_light_bounds
from palubicki.sim.obstacles import AABBObstacle


def test_forest_light_bounds_single_envelope_no_obstacle():
    env = EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, center=(0.0, 0.0, 0.0), shape="ellipsoid")
    origin, size = forest_light_bounds([env], obstacles=[])
    # Envelope AABB: x ∈ ±2, y ∈ ±3, z ∈ ±2
    # 10% pad below/above on x,z → factor 1.2; 10% below + 30% above on y → factor 1.4
    extent = np.array([4.0, 6.0, 4.0])
    expected_origin = np.array([-2.0, -3.0, -2.0]) - 0.1 * extent
    np.testing.assert_allclose(origin, expected_origin)
    expected_size = extent + np.array([0.2 * 4.0, 0.4 * 6.0, 0.2 * 4.0])
    np.testing.assert_allclose(size, expected_size)


def test_forest_light_bounds_multi_envelope_union():
    env_a = EnvelopeConfig(rx=1.0, ry=1.0, rz=1.0, center=(0.0, 0.0, 0.0), shape="ellipsoid")
    env_b = EnvelopeConfig(rx=1.0, ry=1.0, rz=1.0, center=(5.0, 0.0, 0.0), shape="ellipsoid")
    origin, size = forest_light_bounds([env_a, env_b], obstacles=[])
    # AABB union spans x in [-1, 6], y in [-1, 1], z in [-1, 1]
    extent = np.array([7.0, 2.0, 2.0])
    expected_origin = np.array([-1.0, -1.0, -1.0]) - 0.1 * extent
    np.testing.assert_allclose(origin, expected_origin)
    np.testing.assert_allclose(size, extent + np.array([0.2 * 7.0, 0.4 * 2.0, 0.2 * 2.0]))


def test_forest_light_bounds_with_obstacle_extends_aabb():
    env = EnvelopeConfig(rx=1.0, ry=1.0, rz=1.0, center=(0.0, 0.0, 0.0), shape="ellipsoid")
    obstacle = AABBObstacle(ObstacleAABB(min=(10.0, -2.0, -2.0), max=(12.0, 0.0, 2.0)))
    origin, size = forest_light_bounds([env], obstacles=[obstacle])
    # Union AABB: x in [-1, 12], y in [-2, 1], z in [-2, 2]
    extent = np.array([13.0, 3.0, 4.0])
    expected_origin = np.array([-1.0, -2.0, -2.0]) - 0.1 * extent
    np.testing.assert_allclose(origin, expected_origin)
