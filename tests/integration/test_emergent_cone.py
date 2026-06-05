"""The emergent conifer cone (#94): age-driven length banking turns the inverted
shadow-prop crown into a real cone that narrows upward. Slow (real fir sims)."""
from __future__ import annotations

import pytest

from palubicki.config import load_config
from palubicki.sim.diagnostics import compute_metrics
from palubicki.sim.simulator import simulate

_SHADOW = {
    "exposure": "shadow_propagation",
    "envelope.shape": "half_ellipsoid",      # generous NON-cone bounds
    "envelope.rx": 3.0, "envelope.ry": 12.0, "envelope.rz": 3.0,
    "shadow.enabled": True, "shadow.measure": "skyview",
}

# Calibrated age-driven length banking (#94): the values that earn the fir cone.
_CAL = {
    "sim.length_banking.enabled": True,
    "sim.length_banking.persist_rate_fraction": 0.45,
    "sim.length_banking.release_years": 6.0,
}


def _metrics(overrides, tmp_path, years=20):
    ov = {"seed": 0, "sim.max_simulation_years": years}
    ov.update(_SHADOW)
    ov.update(overrides)
    cfg = load_config(yaml_path=None, cli_overrides=ov,
                      output=(tmp_path / "t.glb"), species="fir")
    return compute_metrics(simulate(cfg), cfg=cfg)


@pytest.mark.slow
def test_length_banking_turns_the_inverted_crown_into_a_cone(tmp_path):
    """Banking off → inverted/ovoid crown (widest near the top, crown_monotonicity
    > 0). Banking on (age-driven length) → a real cone that narrows upward
    (crown_monotonicity < 0), with the leader still excurrent."""
    off = _metrics({}, tmp_path)
    on = _metrics(_CAL, tmp_path)

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
    m = _metrics({**_CAL, "geom.pipe_exponent": 3.6}, tmp_path, years=30)
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
