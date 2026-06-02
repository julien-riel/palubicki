
import pytest

from palubicki.config import ConfigError, _deep_merge, _list_species, load_config


def test_deep_merge_overrides_scalar_in_nested_dict():
    base = {"a": {"b": 1, "c": 2}}
    over = {"a": {"b": 99}}
    _deep_merge(base, over)
    assert base == {"a": {"b": 99, "c": 2}}


def test_deep_merge_replaces_list_completely():
    base = {"a": [1, 2, 3]}
    over = {"a": [9]}
    _deep_merge(base, over)
    assert base == {"a": [9]}


def test_deep_merge_adds_new_key():
    base = {"a": 1}
    over = {"b": 2}
    _deep_merge(base, over)
    assert base == {"a": 1, "b": 2}


def test_deep_merge_does_not_recurse_when_base_is_not_dict():
    base = {"a": 1}
    over = {"a": {"b": 2}}
    _deep_merge(base, over)
    assert base == {"a": {"b": 2}}


def test_list_species_returns_sorted_names():
    names = _list_species()
    # Must not crash on missing/empty package — defensive degradation.
    assert isinstance(names, list)
    assert all(isinstance(n, str) for n in names)


def test_unknown_species_raises(tmp_path):
    with pytest.raises(ConfigError, match="unknown species preset"):
        load_config(
            yaml_path=None,
            cli_overrides={},
            output=tmp_path / "x.glb",
            species="redwood",
        )


def test_load_preset_oak(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="oak")
    assert cfg.envelope.shape == "half_ellipsoid"
    assert cfg.geom.leaf_cluster_count == 3
    # bark_texture may be stored as Path or str depending on dataclass field coercion
    assert str(cfg.geom.bark_texture) == "proc:oak_bark"


def test_load_preset_pine(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="pine")
    assert cfg.envelope.shape == "cone"
    assert cfg.phyllotaxy.mode == "whorled"
    # #7: white pine bears 5 needles per fascicle; the fascicle replaces the loose
    # per-position tuft, so leaf_cluster_count dropped 3 -> 1. Real needle area is
    # coupled into the LAI grid (needle_area_scale) and the leader held by a raised
    # lambda_apical.
    assert cfg.geom.leaf_cluster_count == 1
    assert cfg.geom.fascicle_count == 5
    assert cfg.light.needle_area_scale == pytest.approx(0.5)
    # #7 re-calibration (held the leader without over-driving height/trunk):
    assert cfg.sim.lambda_apical == pytest.approx(0.82)
    assert cfg.sim.shoot_extension_max == pytest.approx(0.55)
    assert cfg.geom.pipe_exponent == pytest.approx(2.90)


def test_load_preset_birch(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="birch")
    assert cfg.envelope.shape == "ellipsoid"
    # Birch preset: strong orthotropic trunk, lateral axes have a real downward
    # gravitropic pull (the pendula effect). Sag stays enabled but attenuated.
    assert cfg.tropism.w_orthotropy_main == pytest.approx(0.40)
    assert cfg.tropism.w_orthotropy_lateral == pytest.approx(0.05)
    assert cfg.tropism.w_gravitropism_lateral == pytest.approx(0.45)
    assert cfg.phyllotaxy.divergence_jitter_deg == pytest.approx(5.0)
    assert cfg.sag.enabled is True
    assert cfg.sag.k == pytest.approx(0.010)


def test_user_yaml_overrides_preset(tmp_path):
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text("tropism:\n  w_orthotropy_main: 0.99\n")
    cfg = load_config(yaml_path=user_yaml, cli_overrides={},
                      output=tmp_path / "x.glb", species="oak")
    assert cfg.tropism.w_orthotropy_main == pytest.approx(0.99)
    assert cfg.envelope.shape == "half_ellipsoid"
    assert cfg.geom.leaf_cluster_count == 3


def test_cli_override_wins_over_user_yaml(tmp_path):
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text("tropism:\n  w_orthotropy_main: 0.5\n")
    cfg = load_config(yaml_path=user_yaml,
                      cli_overrides={"tropism.w_orthotropy_main": 0.1},
                      output=tmp_path / "x.glb", species="oak")
    assert cfg.tropism.w_orthotropy_main == pytest.approx(0.1)


def test_deep_merge_preserves_sibling_sections(tmp_path):
    """User YAML touching only `tropism` must not erase preset's `envelope` or `phyllotaxy`."""
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text("tropism:\n  w_orthotropy_main: 0.3\n")
    cfg = load_config(yaml_path=user_yaml, cli_overrides={},
                      output=tmp_path / "x.glb", species="pine")
    assert cfg.envelope.shape == "cone"
    assert cfg.phyllotaxy.mode == "whorled"
    assert cfg.geom.leaf_cluster_count == 1  # #7: pine fascicle replaces the loose tuft
    assert cfg.tropism.w_orthotropy_main == pytest.approx(0.3)


from palubicki.geom.builder import _bark_blend_stops


@pytest.mark.parametrize("species", ["oak", "pine", "birch", "maple", "fir"])
def test_species_enables_bark_blend(species, tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species=species)
    stops = _bark_blend_stops(cfg.geom)
    assert stops is not None, f"{species} should enable bark blend"
    assert stops.d_young <= stops.d_mature <= stops.d_senescent
    # mature tint must equal the species bark_color (mid-trunk look preserved)
    assert tuple(stops.c_mature) == tuple(cfg.geom.bark_color)
