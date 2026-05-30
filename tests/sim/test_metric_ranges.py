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
