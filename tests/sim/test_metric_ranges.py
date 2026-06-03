"""MetricRanges.from_species — loads ✓/✗ bounds from the literature manifest."""
from __future__ import annotations


def test_from_species_none_returns_global_bounds():
    from palubicki.sim.diagnostics import MetricRanges

    r = MetricRanges.from_species(None)
    assert r.horton_bifurcation_ratio_mean == (3.0, 5.0)
    assert r.divergence_angle_deg__order1_mean == (130.0, 145.0)
    assert r.insertion_angle_deg_vs_parent__order1_mean == (50.0, 90.0)


def test_from_species_maple_overrides_divergence_only():
    from palubicki.sim.diagnostics import MetricRanges

    r = MetricRanges.from_species("maple")
    # Decussate (~90deg measured between-node rotation) overrides the spiral
    # golden-angle band.
    assert r.divergence_angle_deg__order1_mean == (80.0, 100.0)
    # Non-overridden fields fall back to the global values.
    assert r.horton_bifurcation_ratio_mean == (3.0, 5.0)
    assert r.insertion_angle_deg_vs_parent__order1_mean == (50.0, 90.0)


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


def test_leader_deviation_deg_is_architectural_field_default_none():
    from palubicki.sim.diagnostics import MetricRanges

    fields = {f.name for f in __import__("dataclasses").fields(MetricRanges)}
    assert "leader_deviation_deg" in fields
    # Default None -> no flag unless a species override supplies a bound.
    assert MetricRanges().leader_deviation_deg is None
    assert MetricRanges.from_species(None).leader_deviation_deg is None


def test_leader_deviation_deg_per_species_bounds():
    from palubicki.sim.diagnostics import MetricRanges

    # Excurrent conifers stand near-vertical (tight upper bound); decurrent /
    # weeping species tolerate a wandering leader (looser). The geometric
    # companion to main_axis_continuation_rate (#48): #43's sparse proxy arched
    # the conifer leaders, which this bound now catches.
    assert MetricRanges.from_species("fir").leader_deviation_deg == (0.0, 20.0)
    assert MetricRanges.from_species("pine").leader_deviation_deg == (0.0, 20.0)
    assert MetricRanges.from_species("birch").leader_deviation_deg == (0.0, 30.0)
    assert MetricRanges.from_species("oak").leader_deviation_deg == (0.0, 35.0)
    assert MetricRanges.from_species("maple").leader_deviation_deg == (0.0, 45.0)


def test_each_species_has_leader_deviation_bound():
    from importlib import resources

    import yaml

    data = yaml.safe_load(
        resources.files("palubicki.configs").joinpath("literature.yaml").read_text()
    )
    species = data["ranges"]["species"]
    for name in ("birch", "fir", "maple", "oak", "pine"):
        assert "leader_deviation_deg" in species[name], (
            f"{name} missing leader_deviation_deg bound"
        )


# ── check_bounds engine (fast; no simulation) ──────────────────────────────
# The slow multi-seed guardrail (#87) leans on these helpers; unit-test the
# resolution + comparison logic here on synthetic metrics so the engine is
# covered without paying for a simulation.

def _birch_multi_seed_metrics(*, crown_radius_mean: float = 3.5) -> dict:
    """A synthetic MULTI-seed metrics dict (scalar leaves wrap into
    {mean, stddev, per_seed}; per-order leaves are {order: {...}}), matching the
    shape `compute_metrics([trees])` returns. All values in-band for birch except
    crown_radius, which the caller dials."""
    def s(mean):
        return {"mean": mean, "stddev": 0.0, "per_seed": [mean]}
    return {
        "tree_height": s(11.0),
        "crown_radius": s(crown_radius_mean),
        "trunk_base_diameter": s(0.18),
        "main_axis_continuation_rate": s(0.67),
        "leader_deviation_deg": s(18.0),
        "horton_bifurcation_ratio_mean": s(3.14),
        "divergence_angle_deg": {1: s(138.0)},
        "insertion_angle_deg_vs_parent": {1: s(82.0)},
    }


def test_gated_fields_lists_every_non_none_bound():
    from palubicki.sim.diagnostics import MetricRanges, gated_fields

    g = gated_fields(MetricRanges.from_species("birch"))
    # The eight bounded fields the manifest gates for a fully-calibrated species.
    assert set(g) == {
        "tree_height", "crown_radius", "trunk_base_diameter",
        "main_axis_continuation_rate", "leader_deviation_deg",
        "horton_bifurcation_ratio_mean",
        "divergence_angle_deg__order1_mean",
        "insertion_angle_deg_vs_parent__order1_mean",
    }
    assert g["crown_radius"] == (2.0, 4.8)  # widened in #87 (see literature.yaml)


def test_gated_fields_skips_unbounded_architectural_fields():
    from palubicki.sim.diagnostics import MetricRanges, gated_fields

    # ash carries only phyllotaxy/topology bounds (decussate divergence override
    # + inherited global insertion/horton); it has no architectural literature
    # numbers, so those fields are None and must not appear as gated.
    g = gated_fields(MetricRanges.from_species("ash"))
    assert set(g) == {
        "horton_bifurcation_ratio_mean",
        "divergence_angle_deg__order1_mean",
        "insertion_angle_deg_vs_parent__order1_mean",
    }
    assert g["divergence_angle_deg__order1_mean"] == (80.0, 100.0)  # decussate


def test_check_bounds_all_in_band_returns_empty():
    from palubicki.sim.diagnostics import MetricRanges, check_bounds

    ranges = MetricRanges.from_species("birch")
    assert check_bounds(_birch_multi_seed_metrics(crown_radius_mean=3.5), ranges) == []


def test_check_bounds_flags_above_band():
    from palubicki.sim.diagnostics import MetricRanges, check_bounds

    ranges = MetricRanges.from_species("birch")
    viols = check_bounds(_birch_multi_seed_metrics(crown_radius_mean=5.0), ranges)
    assert [v.field for v in viols] == ["crown_radius"]
    v = viols[0]
    assert v.kind == "above"
    assert v.value == 5.0
    assert v.bounds == (2.0, 4.8)
    assert "above" in str(v)


def test_check_bounds_flags_below_band():
    from palubicki.sim.diagnostics import MetricRanges, check_bounds

    ranges = MetricRanges.from_species("oak")
    # horton mean dipping under the global abop floor (3.0).
    metrics = {
        "tree_height": 11.0, "crown_radius": 4.2, "trunk_base_diameter": 0.2,
        "main_axis_continuation_rate": 0.9, "leader_deviation_deg": 17.0,
        "horton_bifurcation_ratio_mean": 2.95,
        "divergence_angle_deg": {1: {"mean": 138.0, "stddev": 0.0, "n": 1}},
        "insertion_angle_deg_vs_parent": {1: {"mean": 77.0, "stddev": 0.0, "n": 1}},
    }
    viols = check_bounds(metrics, ranges)
    assert [v.field for v in viols] == ["horton_bifurcation_ratio_mean"]
    assert viols[0].kind == "below"


def test_check_bounds_single_seed_shape_and_order_paths():
    from palubicki.sim.diagnostics import MetricRanges, check_bounds

    # SINGLE-seed shape: scalar leaves are bare floats; per-order leaves are
    # _stats dicts {mean, stddev, n}. The order-path resolution must read ["mean"].
    ranges = MetricRanges.from_species("maple")
    metrics = {
        "tree_height": 8.3, "crown_radius": 4.1, "trunk_base_diameter": 0.14,
        "main_axis_continuation_rate": 0.53, "leader_deviation_deg": 17.0,
        "horton_bifurcation_ratio_mean": 3.07,
        "divergence_angle_deg": {1: {"mean": 89.9, "stddev": 0.0, "n": 10}},
        "insertion_angle_deg_vs_parent": {1: {"mean": 54.5, "stddev": 0.0, "n": 10}},
    }
    assert check_bounds(metrics, ranges) == []


def test_check_bounds_missing_or_nan_is_a_violation():
    from palubicki.sim.diagnostics import MetricRanges, check_bounds

    ranges = MetricRanges.from_species("oak")
    metrics = {
        "tree_height": float("nan"),     # NaN -> unmeasurable
        "divergence_angle_deg": {},       # order 1 absent -> missing
    }
    viols = {
        v.field: v.kind
        for v in check_bounds(
            metrics, ranges,
            fields=["tree_height", "divergence_angle_deg__order1_mean"],
        )
    }
    assert viols == {"tree_height": "missing",
                     "divergence_angle_deg__order1_mean": "missing"}


def test_check_bounds_fields_subset_and_none_bounds_skipped():
    from palubicki.sim.diagnostics import MetricRanges, check_bounds

    # Requesting a field a species never had calibrated (ash tree_height -> None)
    # is skipped, not flagged: you cannot gate what has no bound.
    ranges = MetricRanges.from_species("ash")
    viols = check_bounds(
        {"tree_height": 999.0}, ranges, fields=["tree_height"]
    )
    assert viols == []


def test_resolve_metric_value_tolerates_string_order_keys():
    # A JSON round-trip turns int order keys into strings; resolution must read
    # the value the same as from the live, int-keyed compute_metrics output.
    from palubicki.sim.diagnostics import _resolve_metric_value

    live = {"divergence_angle_deg": {1: {"mean": 138.0}}}
    json_like = {"divergence_angle_deg": {"1": {"mean": 138.0}}}
    assert _resolve_metric_value(live, "divergence_angle_deg__order1_mean") == 138.0
    assert _resolve_metric_value(json_like, "divergence_angle_deg__order1_mean") == 138.0


def test_check_bounds_malformed_scalar_leaf_is_missing_not_error():
    # A scalar leaf that is a dict lacking "mean" must flag a missing violation,
    # not raise on the `dict < float` comparison.
    from palubicki.sim.diagnostics import MetricRanges, check_bounds

    ranges = MetricRanges.from_species("oak")
    viols = check_bounds({"tree_height": {"stddev": 1.0}}, ranges, fields=["tree_height"])
    assert [(v.field, v.kind) for v in viols] == [("tree_height", "missing")]


def test_metric_ranges_insertion_default_matches_manifest_global():
    # The bare-constructor default must agree with the manifest global so there is
    # one source of truth (regression guard for the stale (30,65) default).
    from palubicki.sim.diagnostics import MetricRanges

    assert MetricRanges().insertion_angle_deg_vs_parent__order1_mean == (50.0, 90.0)
    assert (MetricRanges().insertion_angle_deg_vs_parent__order1_mean
            == MetricRanges.from_species(None).insertion_angle_deg_vs_parent__order1_mean)
