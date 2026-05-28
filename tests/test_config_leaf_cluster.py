import pytest

from palubicki.config import (
    Config, ConfigError, EnvelopeConfig, GeomConfig, PhyllotaxyConfig,
    SheddingConfig, SimConfig, TropismConfig,
)


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


def test_leaf_shape_default_is_ovate():
    g = GeomConfig()
    assert g.leaf_shape == "ovate"


def test_leaf_margin_default_is_entire():
    g = GeomConfig()
    assert g.leaf_margin == "entire"


def test_leaf_margin_depth_default_is_zero():
    g = GeomConfig()
    assert g.leaf_margin_depth == 0.0


def test_leaf_margin_count_default_is_zero():
    g = GeomConfig()
    assert g.leaf_margin_count == 0


def test_full_config_rejects_unknown_leaf_shape(tmp_path):
    with pytest.raises(ConfigError, match="leaf_shape"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_shape="banana"),  # type: ignore[arg-type]
            output=tmp_path / "x.glb",
        )


def test_full_config_rejects_unknown_leaf_margin(tmp_path):
    with pytest.raises(ConfigError, match="leaf_margin"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_margin="frilly"),  # type: ignore[arg-type]
            output=tmp_path / "x.glb",
        )


def test_full_config_rejects_margin_depth_out_of_range(tmp_path):
    with pytest.raises(ConfigError, match="leaf_margin_depth"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_margin_depth=1.5),
            output=tmp_path / "x.glb",
        )


def test_full_config_rejects_negative_margin_count(tmp_path):
    with pytest.raises(ConfigError, match="leaf_margin_count"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(leaf_margin_count=-1),
            output=tmp_path / "x.glb",
        )
