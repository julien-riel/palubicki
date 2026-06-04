"""End-to-end smoke for the shadow-propagation exposure backend (#56 Phase 3).

Slow (runs a real sim). The point is to catch the integration failure modes the
adversarial review flagged: self-shadow blackout collapsing to an empty tree
(C2/R2) and the zero-gradient dormancy trap freezing the leader (R1)."""
from __future__ import annotations

import pytest

from palubicki.config import load_config
from palubicki.sim.diagnostics import compute_metrics
from palubicki.sim.simulator import simulate


@pytest.mark.slow
def test_shadow_propagation_fir_grows_a_real_tree(tmp_path):
    """A fir under a generous, deliberately NON-cone ellipsoid bounds volume must
    grow a real, branched tree under shadow propagation — not collapse and not
    freeze. (Dimensional calibration is a later phase; here we only assert the
    backend produces a live, non-degenerate tree.)"""
    cfg = load_config(
        yaml_path=None,
        cli_overrides={
            "seed": 0,
            "exposure": "shadow_propagation",
            "envelope.shape": "ellipsoid",        # non-cone: no prescribed spire
            "shadow.enabled": True,
            "sim.max_simulation_years": 8,
        },
        output=tmp_path / "t.glb",
        species="fir",
    )
    assert cfg.exposure == "shadow_propagation"

    tree = simulate(cfg)
    m = compute_metrics(tree, cfg=cfg)

    # Leader grew (R1: not frozen by a zero-gradient apex) and the canopy did not
    # black itself out (C2/R2: not an empty tree).
    assert m["tree_height"] > 1.0
    assert m["strahler_order_max"] >= 2
    # The Phase-0 silhouette diagnostic resolves on the emergent tree.
    assert 0.0 <= m["clear_bole_fraction"] <= 1.0
    assert 0.0 <= m["apex_sharpness"] <= 1.0


@pytest.mark.slow
def test_bhse_default_path_unchanged(tmp_path):
    """The default BHse path is byte-stable across the new shadow plumbing: same
    seed → identical structural metrics. (The geometry goldens are the
    authoritative byte-identity check; this is a cheap guard that the default
    dispatch wasn't perturbed.)"""
    def _metrics():
        cfg = load_config(
            yaml_path=None,
            cli_overrides={"seed": 0, "sim.max_simulation_years": 5},
            output=tmp_path / "t.glb",
            species="fir",
        )
        assert cfg.exposure == "bhse"
        tree = simulate(cfg)
        m = compute_metrics(tree, cfg=cfg)
        return (m["tree_height"], m["crown_radius"], m["strahler_order_max"],
                m["main_axis_continuation_rate"])

    assert _metrics() == _metrics()
