"""MetricRanges.from_species — loads ✓/✗ bounds from the literature manifest."""
from __future__ import annotations


def test_from_species_none_returns_global_bounds():
    from palubicki.sim.diagnostics import MetricRanges

    r = MetricRanges.from_species(None)
    assert r.horton_bifurcation_ratio_mean == (3.0, 5.0)
    assert r.divergence_angle_deg__order1_mean == (130.0, 145.0)
    assert r.insertion_angle_deg_vs_parent__order1_mean == (30.0, 65.0)


def test_from_species_maple_overrides_divergence_only():
    from palubicki.sim.diagnostics import MetricRanges

    r = MetricRanges.from_species("maple")
    # Decussate (~90deg) overrides the spiral golden-angle band.
    assert r.divergence_angle_deg__order1_mean == (80.0, 100.0)
    # Non-overridden fields fall back to the global values.
    assert r.horton_bifurcation_ratio_mean == (3.0, 5.0)
    assert r.insertion_angle_deg_vs_parent__order1_mean == (30.0, 65.0)


def test_from_species_unknown_falls_back_to_global():
    from palubicki.sim.diagnostics import MetricRanges

    # A species with no manifest override behaves like global.
    r_oak = MetricRanges.from_species("oak")
    r_global = MetricRanges.from_species(None)
    assert r_oak.divergence_angle_deg__order1_mean == r_global.divergence_angle_deg__order1_mean
    assert r_oak.horton_bifurcation_ratio_mean == r_global.horton_bifurcation_ratio_mean


def test_default_ranges_matches_global():
    from palubicki.sim.diagnostics import DEFAULT_RANGES, MetricRanges

    assert MetricRanges.from_species(None) == DEFAULT_RANGES


def test_metric_ranges_has_architectural_fields():
    from palubicki.sim.diagnostics import MetricRanges

    fields = {f.name for f in __import__("dataclasses").fields(MetricRanges)}
    assert "tree_height" in fields
    assert "trunk_base_diameter" in fields
    assert "crown_radius" in fields


def test_architectural_fields_default_none():
    from palubicki.sim.diagnostics import MetricRanges

    r = MetricRanges()
    assert r.tree_height is None
    assert r.crown_radius is None
    assert r.trunk_base_diameter is None


def test_each_species_has_manifest_entry():
    from importlib import resources

    import yaml

    data = yaml.safe_load(
        resources.files("palubicki.configs").joinpath("literature.yaml").read_text()
    )
    species = data["ranges"]["species"]
    for name in ("birch", "fir", "maple", "oak", "pine"):
        assert name in species, f"{name} missing from ranges.species"


def test_oak_divergence_is_spiral_band():
    from palubicki.sim.diagnostics import MetricRanges

    # Quercus is spiral phyllotaxis -> golden-angle band, not decussate.
    assert MetricRanges.from_species("oak").divergence_angle_deg__order1_mean == (130.0, 145.0)


def test_main_axis_continuation_rate_is_architectural_field_default_none():
    from palubicki.sim.diagnostics import MetricRanges

    fields = {f.name for f in __import__("dataclasses").fields(MetricRanges)}
    assert "main_axis_continuation_rate" in fields
    # Default None -> no flag unless a species override supplies a bound.
    assert MetricRanges().main_axis_continuation_rate is None
    assert MetricRanges.from_species(None).main_axis_continuation_rate is None


def test_main_axis_continuation_rate_per_species_bounds():
    from palubicki.sim.diagnostics import MetricRanges

    # Excurrent conifers carry high floors (single dominant leader); the
    # decurrent maple sits low (central leader gives way). Floors all clear
    # the ~0.03 a decapitated leader produces, so the empirical loop flags it.
    assert MetricRanges.from_species("fir").main_axis_continuation_rate == (0.6, 1.0)
    assert MetricRanges.from_species("pine").main_axis_continuation_rate == (0.5, 1.0)
    assert MetricRanges.from_species("oak").main_axis_continuation_rate == (0.45, 1.0)
    assert MetricRanges.from_species("birch").main_axis_continuation_rate == (0.4, 1.0)
    assert MetricRanges.from_species("maple").main_axis_continuation_rate == (0.2, 1.0)


def test_each_species_has_main_axis_continuation_bound():
    from importlib import resources

    import yaml

    data = yaml.safe_load(
        resources.files("palubicki.configs").joinpath("literature.yaml").read_text()
    )
    species = data["ranges"]["species"]
    for name in ("birch", "fir", "maple", "oak", "pine"):
        assert "main_axis_continuation_rate" in species[name], (
            f"{name} missing main_axis_continuation_rate bound"
        )
