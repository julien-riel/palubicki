"""The emergent conifer cone (#94, #96): age-driven length banking turns the
inverted shadow-prop crown into a real cone that narrows upward. Slow (real
conifer sims). Fir is calibrated in #94; pine (whorled, prolific) in #96 — the
same mechanism plus a bounded bud pool (shadow.mortality_enabled + q_dormancy),
without which pine piles up a 200k+ never-pruned cloud and runs away."""
from __future__ import annotations

import pytest

from palubicki.config import load_config
from palubicki.sim.diagnostics import compute_metrics
from palubicki.sim.simulator import simulate

# --- Fir (#94): generous half-ellipsoid NON-cone bounds + age-driven banking. ---
_SHADOW_FIR = {
    "exposure": "shadow_propagation",
    "envelope.shape": "half_ellipsoid",      # generous NON-cone bounds
    "envelope.rx": 3.0, "envelope.ry": 12.0, "envelope.rz": 3.0,
    "shadow.enabled": True, "shadow.measure": "skyview",
}
_CAL_FIR = {
    "sim.length_banking.enabled": True,
    "sim.length_banking.persist_rate_fraction": 0.45,
    "sim.length_banking.release_years": 6.0,
}

# --- Pine (#96): taller, wider, whorled k=5. The cone emerges with the SAME
# age-driven banking, but the prolific bud pool must be bounded or the run is
# intractable (38 min / 9 GB at 30 yr) and the bole over-thickens via the pipe
# model. shadow.mortality_enabled culls the never-established interior cloud
# (banked laterals are protected); q_dormancy=0.5 caps emission; establish_
# threshold=25 fits pine's large vigor scale (q90 banked ~20-40, vs fir's ~0.5);
# pipe_exponent at the 4.0 cap thins the bole into band. ---
_SHADOW_PINE = {
    "exposure": "shadow_propagation",
    "envelope.shape": "half_ellipsoid",      # generous NON-cone bounds
    "envelope.rx": 4.4, "envelope.ry": 20.0, "envelope.rz": 4.4,
    "shadow.enabled": True, "shadow.measure": "skyview",
    "shadow.q_dormancy": 0.5, "shadow.mortality_enabled": True,
    "sim.shade_mortality.light_threshold": 0.50,
}
_CAL_PINE = {
    "sim.length_banking.enabled": True,
    "sim.length_banking.persist_rate_fraction": 0.40,
    "sim.length_banking.release_years": 6.0,
    "sim.length_banking.establish_threshold": 25.0,
    "geom.pipe_exponent": 4.0,
}


def _sim(overrides, tmp_path, years, species, shadow):
    ov = {"seed": 0, "sim.max_simulation_years": years}
    ov.update(shadow)
    ov.update(overrides)
    cfg = load_config(yaml_path=None, cli_overrides=ov,
                      output=(tmp_path / "t.glb"), species=species)
    tree = simulate(cfg)
    return tree, compute_metrics(tree, cfg=cfg)


def _metrics(overrides, tmp_path, years=20, species="fir", shadow=_SHADOW_FIR):
    return _sim(overrides, tmp_path, years, species, shadow)[1]


@pytest.mark.slow
def test_length_banking_turns_the_inverted_crown_into_a_cone(tmp_path):
    """Banking off → inverted/ovoid crown (widest near the top, crown_monotonicity
    > 0). Banking on (age-driven length) → a real cone that narrows upward
    (crown_monotonicity < 0), with the leader still excurrent."""
    off = _metrics({}, tmp_path)
    on = _metrics(_CAL_FIR, tmp_path)

    # Off: the documented inverted/ovoid emergent crown.
    assert off["crown_monotonicity"] > 0.0
    # On: a cone — radius falls with height (Spearman ρ strongly negative).
    assert on["crown_monotonicity"] < -0.5
    # The leader stays a dominant, near-vertical excurrent axis.
    assert on["main_axis_continuation_rate"] >= 0.6
    assert on["leader_deviation_deg"] <= 20.0
    # The crown genuinely flipped, not merely narrowed.
    assert on["crown_monotonicity"] < off["crown_monotonicity"] - 0.5


@pytest.mark.slow
def test_calibrated_cone_dimensions_in_band(tmp_path):
    """At full duration the calibrated emergent cone lands every dimension in the
    fir literature band — height, crown radius, trunk diameter — while staying a
    cone (#94). The cone is genuinely emergent: no envelope.shape: cone."""
    m = _metrics({**_CAL_FIR, "geom.pipe_exponent": 3.6}, tmp_path, years=30)
    assert m["crown_monotonicity"] < -0.5
    assert 1.5 <= m["crown_radius"] <= 2.5
    assert 7.0 <= m["tree_height"] <= 12.0
    assert 0.10 <= m["trunk_base_diameter"] <= 0.20
    assert m["main_axis_continuation_rate"] >= 0.6


@pytest.mark.slow
def test_length_banking_off_is_byte_identical_to_engaged_at_zero(tmp_path):
    """enabled=True with persist_rate_fraction=0 reproduces the off path exactly
    (structural gate, not arithmetic) — the determinism guard for the flag."""
    off = _metrics({}, tmp_path, years=12)
    zero = _metrics({"sim.length_banking.enabled": True,
                     "sim.length_banking.persist_rate_fraction": 0.0}, tmp_path, years=12)
    assert (off["tree_height"], off["crown_radius"], off["strahler_order_max"]) == \
           (zero["tree_height"], zero["crown_radius"], zero["strahler_order_max"])


@pytest.mark.slow
def test_pine_emergent_cone_under_bounded_shadow_propagation(tmp_path):
    """Pine (whorled k=5) grows the SAME age-driven emergent cone as fir once the
    bud pool is bounded (#96). Run at y20 — by which the cone, the excurrent leader
    and the in-band trunk are established — to keep this heavy species tractable;
    the full literature band (height 12-18 m, crown 2.5-4.0 m) is reached at y30
    and verified by the multi-seed sweep documented in realism-assessment.md
    (y30 seed-0: mono -0.93, h 16.1, crown 3.63, trunk 0.258 — all in band).

    The internode bound is the regression guard for the pool-bounding mechanism:
    without shadow.mortality_enabled + q_dormancy pine emits 280k+ internodes at
    y20 (and runs away by y30); the bounded run stays well under 120k."""
    tree, m = _sim(_CAL_PINE, tmp_path, years=20, species="pine", shadow=_SHADOW_PINE)
    # A real cone, narrowing upward (was the inverted ovoid before banking).
    assert m["crown_monotonicity"] < -0.5
    # The leader stays a dominant, near-vertical excurrent axis.
    assert m["main_axis_continuation_rate"] >= 0.6
    assert m["leader_deviation_deg"] <= 20.0
    # Trunk already in the pine literature band at y20 (pipe-model + bounded pool).
    assert 0.18 <= m["trunk_base_diameter"] <= 0.35
    # Crown on its way to the band (2.5-4.0 at y30); guard the lower side at y20.
    assert m["crown_radius"] >= 1.8
    # The pool stayed bounded — the mortality mechanism is doing its job.
    assert len(tree.all_internodes) < 120_000
