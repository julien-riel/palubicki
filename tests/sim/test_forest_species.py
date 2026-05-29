import pytest

from palubicki.config import (
    Config,
    EnvelopeConfig,
    ForestSeed,
    GeomConfig,
    PhyllotaxyConfig,
    SheddingConfig,
    SimConfig,
    TropismConfig,
    load_config,
)
from palubicki.sim.forest import per_tree_config


def _bare_cfg(tmp_path) -> Config:
    return Config(
        envelope=EnvelopeConfig(),
        sim=SimConfig(),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        output=tmp_path / "x.glb",
        seed=0,
    )


def test_forest_seed_accepts_species_field():
    s = ForestSeed(position=(0.0, 0.0, 0.0), species="oak")
    assert s.species == "oak"


def test_per_tree_config_applies_oak_preset(tmp_path):
    cfg = _bare_cfg(tmp_path)
    seed_entry = ForestSeed(position=(0.0, 0.0, 0.0), species="oak")
    derived = per_tree_config(cfg, seed_entry, tree_index=0)
    assert derived.envelope.shape == "half_ellipsoid"
    assert derived.envelope.rx == pytest.approx(5.0)
    assert derived.phyllotaxy.branch_angle_by_order == (60.0, 40.0, 30.0, 25.0)
    assert derived.envelope.center == (0.0, 0.0, 0.0)


def test_per_tree_config_overrides_win_over_species(tmp_path):
    cfg = _bare_cfg(tmp_path)
    seed_entry = ForestSeed(
        position=(0.0, 0.0, 0.0),
        species="oak",
        overrides={"tropism.w_orthotropy_main": 0.99},
    )
    derived = per_tree_config(cfg, seed_entry, tree_index=0)
    assert derived.tropism.w_orthotropy_main == pytest.approx(0.99)
    assert derived.envelope.shape == "half_ellipsoid"  # oak preserved


def test_yaml_forest_with_species_per_seed_parses(tmp_path):
    yaml_path = tmp_path / "forest.yaml"
    yaml_path.write_text(
        "envelope:\n"
        "  marker_count: 500\n"
        "sim:\n"
        "  max_iterations: 4\n"
        "forest:\n"
        "  seeds:\n"
        "    - position: [0.0, 0.0, 0.0]\n"
        "      species: oak\n"
        "    - position: [10.0, 0.0, 0.0]\n"
        "      species: pine\n"
    )
    cfg = load_config(yaml_path=yaml_path, cli_overrides={},
                      output=tmp_path / "x.glb")
    assert len(cfg.forest.seeds) == 2
    assert cfg.forest.seeds[0].species == "oak"
    assert cfg.forest.seeds[1].species == "pine"
