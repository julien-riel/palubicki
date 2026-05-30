# tests/test_config.py
from pathlib import Path

import pytest

from palubicki.config import (
    Config,
    ConfigError,
    EnvelopeConfig,
    GeomConfig,
    PhyllotaxyConfig,
    SheddingConfig,
    SimConfig,
    TropismConfig,
    load_config,
)


def _make_config(**overrides):
    from palubicki.config import LightConfig
    base = {
        "envelope": EnvelopeConfig(shape="ellipsoid", rx=1.0, ry=1.0, rz=1.0),
        "sim": SimConfig(),
        "tropism": TropismConfig(),
        "phyllotaxy": PhyllotaxyConfig(),
        "shedding": SheddingConfig(),
        "geom": GeomConfig(),
        "light": LightConfig(),
    }
    base.update(overrides)
    return Config(**base)


def test_config_with_defaults_is_valid(tmp_path):
    cfg = _make_config(output=tmp_path / "out.glb")
    assert cfg.sim.max_simulation_years == 30.0
    assert cfg.tropism.w_orthotropy_main == 0.3
    assert cfg.tropism.w_orthotropy_lateral == 0.1
    assert cfg.tropism.w_gravitropism_main == 0.0
    assert cfg.tropism.w_gravitropism_lateral == 0.0


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


def test_light_config_defaults():
    from palubicki.config import LightConfig
    c = LightConfig()
    assert c.enabled is False
    assert c.grid_origin is None
    assert c.grid_size is None
    assert c.grid_resolution == (64, 64, 64)
    assert c.k_absorption == 0.5
    assert c.leaf_area == 0.04
    assert c.internode_area_scale == 1.0
    assert c.n_rays == 16
    assert c.light_direction == (0.0, 1.0, 0.0)


def test_light_config_validation_rejects_zero_rays(tmp_path):
    from palubicki.config import (
        Config,
        ConfigError,
        EnvelopeConfig,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    with pytest.raises(ConfigError, match="n_rays"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(),
            light=LightConfig(n_rays=0),
            output=tmp_path / "x.glb",
        )


def test_light_config_validation_rejects_negative_k_absorption(tmp_path):
    from palubicki.config import (
        Config,
        ConfigError,
        EnvelopeConfig,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    with pytest.raises(ConfigError, match="k_absorption"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(),
            light=LightConfig(k_absorption=-0.1),
            output=tmp_path / "x.glb",
        )


def test_config_default_light_is_disabled(tmp_path):
    from palubicki.config import (
        Config,
        EnvelopeConfig,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    c = Config(
        envelope=EnvelopeConfig(), sim=SimConfig(), tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(), shedding=SheddingConfig(), geom=GeomConfig(),
        light=LightConfig(),
        output=tmp_path / "x.glb",
    )
    assert c.light.enabled is False


def test_light_config_validation_rejects_zero_light_direction(tmp_path):
    from palubicki.config import (
        Config,
        ConfigError,
        EnvelopeConfig,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    with pytest.raises(ConfigError, match="light_direction"):
        Config(
            envelope=EnvelopeConfig(),
            sim=SimConfig(),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(),
            geom=GeomConfig(),
            light=LightConfig(light_direction=(0.0, 0.0, 0.0)),
            output=tmp_path / "x.glb",
        )


def test_obstacle_aabb_defaults():
    from palubicki.config import ObstacleAABB
    o = ObstacleAABB()
    assert o.kind == "aabb"
    assert o.min == (0.0, 0.0, 0.0)
    assert o.max == (1.0, 1.0, 1.0)


def test_obstacle_sphere_defaults():
    from palubicki.config import ObstacleSphere
    o = ObstacleSphere()
    assert o.kind == "sphere"
    assert o.center == (0.0, 0.0, 0.0)
    assert o.radius == 1.0


def test_obstacle_obb_defaults():
    from palubicki.config import ObstacleOBB
    o = ObstacleOBB()
    assert o.kind == "obb"
    assert o.center == (0.0, 0.0, 0.0)
    assert o.half_extents == (1.0, 1.0, 1.0)
    assert o.axes == (1, 0, 0, 0, 1, 0, 0, 0, 1)


def test_obstacle_mesh_defaults():
    from pathlib import Path

    from palubicki.config import ObstacleMesh
    o = ObstacleMesh(path=Path("foo.obj"))
    assert o.kind == "mesh"
    assert o.path == Path("foo.obj")
    assert o.translate == (0.0, 0.0, 0.0)
    assert o.scale == 1.0


def test_forest_seed_defaults():
    from palubicki.config import ForestSeed
    s = ForestSeed(position=(1.0, 0.0, 2.0))
    assert s.position == (1.0, 0.0, 2.0)
    assert s.seed is None
    assert s.overrides == {}


def test_forest_config_defaults():
    from palubicki.config import ForestConfig
    f = ForestConfig()
    assert f.seeds == ()
    assert f.obstacles == ()
    assert f.export_obstacles_geometry is True


def test_config_default_forest_is_empty():
    from pathlib import Path

    from palubicki.config import (
        Config,
        EnvelopeConfig,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    c = Config(
        envelope=EnvelopeConfig(), sim=SimConfig(), tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(), shedding=SheddingConfig(), geom=GeomConfig(),
        light=LightConfig(), output=Path("/tmp/x.glb"),
    )
    assert c.forest.seeds == ()
    assert c.forest.obstacles == ()


def test_config_rejects_negative_w_orthotropy_main(tmp_path):
    with pytest.raises(ConfigError, match="w_orthotropy_main"):
        _make_config(
            tropism=TropismConfig(w_orthotropy_main=-0.1),
            output=tmp_path / "out.glb",
        )


def test_config_rejects_negative_w_gravitropism_lateral(tmp_path):
    with pytest.raises(ConfigError, match="w_gravitropism_lateral"):
        _make_config(
            tropism=TropismConfig(w_gravitropism_lateral=-0.2),
            output=tmp_path / "out.glb",
        )


def test_config_rejects_internode_length_jitter_above_cap(tmp_path):
    with pytest.raises(ConfigError, match="internode_length_jitter"):
        _make_config(
            sim=SimConfig(internode_length_jitter=0.6),
            output=tmp_path / "out.glb",
        )


def test_config_rejects_negative_internode_length_jitter(tmp_path):
    with pytest.raises(ConfigError, match="internode_length_jitter"):
        _make_config(
            sim=SimConfig(internode_length_jitter=-0.05),
            output=tmp_path / "out.glb",
        )


def test_sympodial_config_defaults():
    from palubicki.config import SympodialConfig
    s = SympodialConfig()
    assert s.enabled is False
    assert s.q_threshold == 1.0
    assert s.n_consecutive_steps == 3


def test_sim_config_has_sympodial_default(tmp_path):
    from palubicki.config import SympodialConfig
    cfg = _make_config(output=tmp_path / "out.glb")
    assert isinstance(cfg.sim.sympodial, SympodialConfig)
    assert cfg.sim.sympodial.enabled is False


def test_sympodial_q_threshold_negative_raises(tmp_path):
    from palubicki.config import SimConfig, SympodialConfig
    with pytest.raises(ConfigError, match="q_threshold"):
        _make_config(
            sim=SimConfig(sympodial=SympodialConfig(q_threshold=-0.1)),
            output=tmp_path / "out.glb",
        )


def test_sympodial_n_consecutive_steps_zero_raises(tmp_path):
    from palubicki.config import SimConfig, SympodialConfig
    with pytest.raises(ConfigError, match="n_consecutive_steps"):
        _make_config(
            sim=SimConfig(sympodial=SympodialConfig(n_consecutive_steps=0)),
            output=tmp_path / "out.glb",
        )


def test_phyllotaxy_branch_angle_by_order_default():
    from palubicki.config import PhyllotaxyConfig
    p = PhyllotaxyConfig()
    assert p.branch_angle_by_order == (45.0,)
    assert not hasattr(p, "branch_angle_deg")


def test_phyllotaxy_branch_angle_by_order_empty_raises(tmp_path):
    from palubicki.config import PhyllotaxyConfig
    with pytest.raises(ConfigError, match="at least one element"):
        _make_config(
            phyllotaxy=PhyllotaxyConfig(branch_angle_by_order=()),
            output=tmp_path / "out.glb",
        )


def test_phyllotaxy_branch_angle_by_order_out_of_range_raises(tmp_path):
    from palubicki.config import PhyllotaxyConfig
    with pytest.raises(ConfigError, match=r"branch_angle_by_order\[0\]"):
        _make_config(
            phyllotaxy=PhyllotaxyConfig(branch_angle_by_order=(120.0,)),
            output=tmp_path / "out.glb",
        )


def test_phyllotaxy_branch_angle_by_order_negative_raises(tmp_path):
    from palubicki.config import PhyllotaxyConfig
    with pytest.raises(ConfigError, match=r"branch_angle_by_order\[1\]"):
        _make_config(
            phyllotaxy=PhyllotaxyConfig(branch_angle_by_order=(45.0, -5.0)),
            output=tmp_path / "out.glb",
        )


def test_tropism_plagiotropism_defaults(tmp_path):
    cfg = _make_config(output=tmp_path / "out.glb")
    assert cfg.tropism.w_plagiotropism_main == 0.0
    assert cfg.tropism.w_plagiotropism_lateral == 0.0


def test_tropism_plagiotropism_negative_main_raises(tmp_path):
    with pytest.raises(ConfigError, match="w_plagiotropism_main"):
        _make_config(
            tropism=TropismConfig(w_plagiotropism_main=-0.1),
            output=tmp_path / "out.glb",
        )


def test_tropism_plagiotropism_negative_lateral_raises(tmp_path):
    with pytest.raises(ConfigError, match="w_plagiotropism_lateral"):
        _make_config(
            tropism=TropismConfig(w_plagiotropism_lateral=-0.5),
            output=tmp_path / "out.glb",
        )


def test_shade_mortality_config_defaults():
    from palubicki.config import ShadeMortalityConfig
    c = ShadeMortalityConfig()
    assert c.enabled is False
    assert c.light_threshold == 0.15
    assert c.n_consecutive_steps == 3


def test_config_includes_shade_mortality(tmp_path):
    from palubicki.config import ShadeMortalityConfig
    cfg = _make_config(output=tmp_path / "out.glb")
    assert isinstance(cfg.sim.shade_mortality, ShadeMortalityConfig)
    assert cfg.sim.shade_mortality.enabled is False


def test_config_rejects_light_threshold_out_of_range(tmp_path):
    from palubicki.config import ShadeMortalityConfig
    with pytest.raises(ConfigError, match="light_threshold"):
        _make_config(
            sim=SimConfig(shade_mortality=ShadeMortalityConfig(light_threshold=1.5)),
            output=tmp_path / "out.glb",
        )


def test_config_rejects_n_consecutive_steps_zero(tmp_path):
    from palubicki.config import ShadeMortalityConfig
    with pytest.raises(ConfigError, match="n_consecutive_steps"):
        _make_config(
            sim=SimConfig(shade_mortality=ShadeMortalityConfig(n_consecutive_steps=0)),
            output=tmp_path / "out.glb",
        )


def test_config_rejects_shade_mortality_enabled_without_light(tmp_path):
    from palubicki.config import LightConfig, ShadeMortalityConfig
    with pytest.raises(ConfigError, match="shade_mortality.*light"):
        _make_config(
            sim=SimConfig(shade_mortality=ShadeMortalityConfig(enabled=True)),
            light=LightConfig(enabled=False),
            output=tmp_path / "out.glb",
        )


def test_phyllotaxy_dormant_reserve_count_default():
    p = PhyllotaxyConfig()
    assert p.dormant_reserve_count == 0


def test_config_rejects_negative_dormant_reserve_count(tmp_path):
    with pytest.raises(ConfigError, match="dormant_reserve_count"):
        _make_config(
            phyllotaxy=PhyllotaxyConfig(dormant_reserve_count=-1),
            output=tmp_path / "out.glb",
        )


def test_shedding_reactivation_count_default():
    s = SheddingConfig()
    assert s.reactivation_count == 1


def test_config_rejects_negative_reactivation_count(tmp_path):
    with pytest.raises(ConfigError, match="reactivation_count"):
        _make_config(
            shedding=SheddingConfig(reactivation_count=-1),
            output=tmp_path / "out.glb",
        )


def test_phyllotaxy_mode_decussate_is_accepted(tmp_path):
    cfg = _make_config(
        phyllotaxy=PhyllotaxyConfig(mode="decussate", divergence_angle_deg=0.0),
        output=tmp_path / "out.glb",
    )
    assert cfg.phyllotaxy.mode == "decussate"


def test_geom_leaf_sun_shade_k_default_zero(tmp_path):
    g = GeomConfig()
    assert g.leaf_sun_shade_k == 0.0


def test_geom_leaf_sun_shade_k_negative_rejected(tmp_path):
    with pytest.raises(ConfigError, match="leaf_sun_shade_k"):
        _make_config(
            geom=GeomConfig(leaf_sun_shade_k=-0.1),
            output=tmp_path / "x.glb",
        )


def test_geom_leaf_sun_shade_k_above_two_rejected(tmp_path):
    with pytest.raises(ConfigError, match="leaf_sun_shade_k"):
        _make_config(
            geom=GeomConfig(leaf_sun_shade_k=2.5),
            output=tmp_path / "x.glb",
        )


def test_elongation_defaults_disabled():
    from palubicki.config import ElongationConfig
    cfg = ElongationConfig()
    assert cfg.enabled is False
    assert cfg.tau_years == 3.0


def test_sim_config_has_elongation_subdataclass():
    from palubicki.config import ElongationConfig, SimConfig
    s = SimConfig()
    assert isinstance(s.elongation, ElongationConfig)
    assert s.elongation.enabled is False


def test_elongation_validation_tau_must_be_positive(tmp_path):
    from palubicki.config import ConfigError, load_config
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text("sim:\n  elongation:\n    enabled: true\n    tau_years: 0.0\n")
    with pytest.raises(ConfigError, match="tau_years"):
        load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")


def test_bud_break_bias_defaults_to_uniform(tmp_path: Path) -> None:
    yaml_path = tmp_path / "c.yaml"
    yaml_path.write_text("sim: {}\n")
    cfg = load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")
    assert cfg.sim.bud_break_bias.mode == "uniform"
    assert cfg.sim.bud_break_bias.strength == 0.0


def test_bud_break_bias_loads_from_yaml(tmp_path: Path) -> None:
    yaml_path = tmp_path / "c.yaml"
    yaml_path.write_text(
        "sim:\n"
        "  bud_break_bias:\n"
        "    mode: basitonic\n"
        "    strength: 0.6\n"
    )
    cfg = load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")
    assert cfg.sim.bud_break_bias.mode == "basitonic"
    assert cfg.sim.bud_break_bias.strength == pytest.approx(0.6)


def test_bud_break_bias_rejects_invalid_mode(tmp_path: Path) -> None:
    yaml_path = tmp_path / "c.yaml"
    yaml_path.write_text(
        "sim:\n"
        "  bud_break_bias:\n"
        "    mode: anisotonic\n"
        "    strength: 0.5\n"
    )
    with pytest.raises(ConfigError, match="bud_break_bias.mode"):
        load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")


def test_bud_break_bias_rejects_out_of_range_strength(tmp_path: Path) -> None:
    yaml_path = tmp_path / "c.yaml"
    yaml_path.write_text(
        "sim:\n"
        "  bud_break_bias:\n"
        "    mode: acrotonic\n"
        "    strength: 1.5\n"
    )
    with pytest.raises(ConfigError, match="bud_break_bias.strength"):
        load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")


def test_bud_break_bias_rejects_unknown_key(tmp_path: Path) -> None:
    yaml_path = tmp_path / "c.yaml"
    yaml_path.write_text(
        "sim:\n"
        "  bud_break_bias:\n"
        "    mode: uniform\n"
        "    strength: 0.0\n"
        "    bogus: 1\n"
    )
    with pytest.raises(ConfigError, match="bud_break_bias"):
        load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")


def _geom_cfg(**geom_kwargs):
    return Config(
        envelope=EnvelopeConfig(), sim=SimConfig(), tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(), shedding=SheddingConfig(),
        geom=GeomConfig(**geom_kwargs),
    )


def test_flare_defaults_present():
    from palubicki.config import GeomConfig
    g = GeomConfig()
    assert g.root_flare_height == 0.3
    assert g.root_flare_factor == 1.6
    assert g.root_flare_falloff == "linear"
    assert g.root_buttress_count == 0
    assert g.root_buttress_amplitude == 0.15
    assert g.root_flare_variation == 0.08


def test_flare_factor_below_one_rejected():
    with pytest.raises(ConfigError, match="root_flare_factor"):
        _geom_cfg(root_flare_factor=0.9)  # raises in __post_init__


def test_buttress_amplitude_out_of_range_rejected():
    with pytest.raises(ConfigError, match="root_buttress_amplitude"):
        _geom_cfg(root_buttress_amplitude=1.0)


def test_flare_variation_out_of_range_rejected():
    with pytest.raises(ConfigError, match="root_flare_variation"):
        _geom_cfg(root_flare_variation=1.5)


def test_geomconfig_blend_off_by_default():
    g = GeomConfig()
    assert g.bark_tint_young is None
    assert g.bark_tint_mature is None
    assert g.bark_tint_senescent is None
    # default stops present and ordered
    assert g.bark_blend_diameter_young <= g.bark_blend_diameter_mature <= g.bark_blend_diameter_senescent


def test_geomconfig_accepts_tints():
    g = GeomConfig(
        bark_tint_young=(0.45, 0.38, 0.30),
        bark_tint_mature=(0.35, 0.22, 0.12),
        bark_tint_senescent=(0.22, 0.20, 0.16),
    )
    assert g.bark_tint_young == (0.45, 0.38, 0.30)


def test_sim_config_time_defaults():
    from palubicki.config import SimConfig
    s = SimConfig()
    assert s.dt_years == 1.0
    assert s.max_simulation_years == 30.0
    assert s.annual_growth_period == (0.0, 1.0)
    assert s.num_iterations == 30


def test_num_iterations_quarterly():
    from palubicki.config import SimConfig
    s = SimConfig(dt_years=0.25, max_simulation_years=10.0)
    assert s.num_iterations == 40


def test_dt_years_must_be_positive(tmp_path):
    from palubicki.config import ConfigError, load_config
    p = tmp_path / "bad.yaml"
    p.write_text("sim:\n  dt_years: 0.0\n")
    with pytest.raises(ConfigError, match="dt_years"):
        load_config(yaml_path=p, cli_overrides={}, output=tmp_path / "o.glb")


def test_annual_growth_period_must_be_ordered(tmp_path):
    from palubicki.config import ConfigError, load_config
    p = tmp_path / "bad.yaml"
    p.write_text("sim:\n  annual_growth_period: [0.6, 0.3]\n")
    with pytest.raises(ConfigError, match="annual_growth_period"):
        load_config(yaml_path=p, cli_overrides={}, output=tmp_path / "o.glb")


def test_annual_growth_period_parsed_from_yaml(tmp_path):
    from palubicki.config import load_config
    p = tmp_path / "ok.yaml"
    p.write_text("sim:\n  annual_growth_period: [0.25, 0.55]\n")
    cfg = load_config(yaml_path=p, cli_overrides={}, output=tmp_path / "o.glb")
    assert cfg.sim.annual_growth_period == (0.25, 0.55)


def test_simconfig_has_vigor_fields_with_defaults():
    from palubicki.config import SimConfig
    s = SimConfig()
    assert s.shoot_extension_max > 0
    assert s.vigor_ref > 0
    assert s.vigor_dormancy >= 0
    assert 0 < s.vigor_smoothing <= 1
    assert s.vigor_diameter_gain >= 0


def test_simconfig_dropped_obsolete_fields():
    from palubicki.config import SimConfig
    s = SimConfig()
    assert not hasattr(s, "internode_length")
    assert not hasattr(s, "n_substeps_max")
    assert not hasattr(s, "re_perceive_per_substep")


def test_simconfig_dropped_age_factor_fields():
    from palubicki.config import ElongationConfig
    e = ElongationConfig()
    assert not hasattr(e, "age_factor_min")
    assert not hasattr(e, "age_factor_decay")


def test_invalid_vigor_ref_raises(tmp_path):
    with pytest.raises(ConfigError, match="vigor_ref"):
        _make_config(
            sim=SimConfig(vigor_ref=0.0),
            output=tmp_path / "out.glb",
        )


def test_tropism_epinasty_defaults_off():
    from palubicki.config import TropismConfig
    c = TropismConfig()
    assert c.epinasty_enabled is False
    assert c.epinasty_tau_years == 8.0


def test_tropism_epinasty_tau_years_zero_raises(tmp_path):
    with pytest.raises(ConfigError, match="epinasty_tau_years"):
        _make_config(
            tropism=TropismConfig(epinasty_enabled=True, epinasty_tau_years=0.0),
            output=tmp_path / "out.glb",
        )


def test_tropism_epinasty_disabled_with_zero_tau_is_valid(tmp_path):
    # When disabled, tau_years is not validated — must NOT raise.
    cfg = _make_config(
        tropism=TropismConfig(epinasty_enabled=False, epinasty_tau_years=0.0),
        output=tmp_path / "out.glb",
    )
    assert cfg.tropism.epinasty_tau_years == 0.0
