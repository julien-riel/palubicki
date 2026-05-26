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
