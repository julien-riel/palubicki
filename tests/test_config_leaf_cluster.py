import pytest

from palubicki.config import ConfigError, GeomConfig


def test_leaf_cluster_defaults_are_v1_compat():
    g = GeomConfig()
    assert g.leaf_cluster_count == 1
    assert g.leaf_aspect == 1.0
    assert g.leaf_splay_deg == 0.0


def test_leaf_cluster_count_zero_invalid_at_config_validation():
    """GeomConfig itself is permissive (no __post_init__); validation lives in Config.
    We exercise it via a full Config construction in the next test."""
    g = GeomConfig(leaf_cluster_count=0)
    assert g.leaf_cluster_count == 0  # accepted at the dataclass level


def test_full_config_rejects_zero_cluster_count(tmp_path):
    from palubicki.config import (
        Config, EnvelopeConfig, LightConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    with pytest.raises(ConfigError, match="leaf_cluster_count"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_cluster_count=0),
            output=tmp_path / "x.glb",
        )


def test_full_config_rejects_aspect_out_of_range(tmp_path):
    from palubicki.config import (
        Config, EnvelopeConfig, LightConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    with pytest.raises(ConfigError, match="leaf_aspect"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_aspect=5.0),
            output=tmp_path / "x.glb",
        )


def test_full_config_rejects_splay_out_of_range(tmp_path):
    from palubicki.config import (
        Config, EnvelopeConfig, LightConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    with pytest.raises(ConfigError, match="leaf_splay_deg"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_splay_deg=120.0),
            output=tmp_path / "x.glb",
        )
