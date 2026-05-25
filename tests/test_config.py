# tests/test_config.py
from pathlib import Path

import pytest

from palubicki.config import (
    Config, ConfigError, EnvelopeConfig, GeomConfig, PhyllotaxyConfig,
    SheddingConfig, SimConfig, TropismConfig,
)


def _make_config(**overrides):
    base = dict(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=1.0, ry=1.0, rz=1.0),
        sim=SimConfig(),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
    )
    base.update(overrides)
    return Config(**base)


def test_config_with_defaults_is_valid(tmp_path):
    cfg = _make_config(output=tmp_path / "out.glb")
    assert cfg.sim.max_iterations == 30
    assert cfg.tropism.w_gravity == 0.3


def test_config_rejects_zero_radius(tmp_path):
    with pytest.raises(ConfigError, match="rx"):
        _make_config(
            envelope=EnvelopeConfig(shape="sphere", rx=0.0, ry=1.0, rz=1.0),
            output=tmp_path / "out.glb",
        )


def test_config_rejects_lambda_out_of_range(tmp_path):
    with pytest.raises(ConfigError, match="lambda"):
        _make_config(
            sim=SimConfig(lambda_apical=1.5),
            output=tmp_path / "out.glb",
        )


def test_config_rejects_missing_output_parent(tmp_path):
    with pytest.raises(ConfigError, match="output"):
        _make_config(output=tmp_path / "nonexistent" / "out.glb")


def test_config_rejects_ring_sides_too_low(tmp_path):
    with pytest.raises(ConfigError, match="ring_sides"):
        _make_config(geom=GeomConfig(ring_sides=2), output=tmp_path / "out.glb")


def test_config_rejects_negative_r_perception(tmp_path):
    with pytest.raises(ConfigError, match="r_perception"):
        _make_config(
            sim=SimConfig(r_perception=-0.1),
            output=tmp_path / "out.glb",
        )


def test_config_rejects_zero_r_tip(tmp_path):
    with pytest.raises(ConfigError, match="r_tip"):
        _make_config(
            geom=GeomConfig(r_tip=0),
            output=tmp_path / "out.glb",
        )
