"""End-to-end smoke for the shadow-propagation exposure backend (#56).

Slow (runs real sims). Asserts the backend produces a live, excurrent-leader tree
under both exposure measures and that apical control measurably tapers the upper
crown. It does NOT assert a conifer cone: pure-emergent form under light
competition is ovoid/inverted (the lowest branches are shaded-short rather than
longest) — a branch-length-dynamics limitation tracked as a follow-up. The
silhouette drift vs the cone-seeded BHse fir is recorded, not gated."""
from __future__ import annotations

import pytest

from palubicki.config import load_config
from palubicki.sim.diagnostics import compute_metrics, silhouette_drift
from palubicki.sim.simulator import simulate

_SP = {
    "exposure": "shadow_propagation",
    "envelope.shape": "half_ellipsoid",
    "envelope.rx": 3.0, "envelope.ry": 12.0, "envelope.rz": 3.0,
    "shadow.enabled": True,
}


def _run(overrides, years=20, seed=0, tmp_path=None):
    ov = {"seed": seed, "sim.max_simulation_years": years}
    ov.update(overrides)
    cfg = load_config(yaml_path=None, cli_overrides=ov,
                      output=(tmp_path / "t.glb"), species="fir")
    return compute_metrics(simulate(cfg), cfg=cfg)


@pytest.mark.slow
@pytest.mark.parametrize("measure", ["skyview", "pyramid"])
def test_shadow_backend_grows_excurrent_tree(measure, tmp_path):
    """Both exposure measures produce a real, branched tree with a dominant,
    near-vertical leader — no blackout (C2/R2), no frozen leader (R1)."""
    m = _run({**_SP, "shadow.measure": measure}, tmp_path=tmp_path)
    assert m["tree_height"] > 1.0
    assert m["strahler_order_max"] >= 2
    assert m["main_axis_continuation_rate"] >= 0.6     # excurrent leader
    assert m["leader_deviation_deg"] <= 20.0           # near-vertical
    assert 0.0 <= m["apex_sharpness"] <= 1.0


@pytest.mark.slow
def test_apical_control_tapers_the_upper_crown(tmp_path):
    """Acropetal apical control narrows the top of the crown — apex_sharpness with
    control on is below control off (a partial taper; the full cone is deferred)."""
    base = {**_SP, "shadow.measure": "skyview",
            "shadow.quality_scale": 8.0, "sim.lambda_apical": 0.94}
    off = _run(base, years=30, tmp_path=tmp_path)
    on = _run({**base, "sim.apical_control_length": 8.0}, years=30, tmp_path=tmp_path)
    assert on["apex_sharpness"] < off["apex_sharpness"]


@pytest.mark.slow
def test_silhouette_drift_vs_cone_bhse_is_measurable(tmp_path):
    """The AC3 diagnostic resolves between the cone-seeded BHse fir and the
    neutral-bounds shadow-prop fir. Recorded, not gated (the form gap is the
    documented finding, not a regression to guard)."""
    ref = _run({}, years=30, tmp_path=tmp_path)               # shipped BHse cone
    sp = _run({**_SP, "shadow.measure": "skyview"}, years=30, tmp_path=tmp_path)
    drift = silhouette_drift(sp, ref)
    assert drift == drift and drift >= 0.0                    # finite, non-negative


@pytest.mark.slow
def test_bhse_default_path_unchanged(tmp_path):
    """The default BHse path is deterministic across the shadow plumbing."""
    a = _run({}, years=15, tmp_path=tmp_path)
    b = _run({}, years=15, tmp_path=tmp_path)
    assert (a["tree_height"], a["crown_radius"], a["strahler_order_max"]) == \
           (b["tree_height"], b["crown_radius"], b["strahler_order_max"])
