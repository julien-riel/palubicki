"""Verify emergent tapering: distal internodes are shorter than proximal ones.

#20 replaced the top-down age_factor(birth_time) length clock with vigor-driven
length: internode length emerges from the Borchert-Honda flux v_b, which falls
off toward the distal tips as markers deplete. So tapering is now a function of
POSITION along the tree (proximal trunk vs distal twigs), not of birth time — a
late-born internode on a vigorous proximal axis can be longer than an early-born
distal one. This test asserts the position-based tapering on a full oak via the
diagnostics harness (the #20 acceptance criterion).
"""
import pytest


@pytest.mark.slow
def test_oak_distal_internodes_shorter_than_proximal(tmp_path):
    from palubicki.config import load_config
    from palubicki.sim.diagnostics import compute_metrics
    from palubicki.sim.simulator import simulate

    cfg = load_config(
        yaml_path=None,
        cli_overrides={
            # 8000 markers (oak's real preset is 25000) sustains a multi-year tree
            # (~1000+ internodes) so proximal and distal axis-order bands are both
            # well-populated for the tapering comparison.
            "envelope.marker_count": 8000,
            "sim.max_simulation_years": 30,
        },
        output=tmp_path / "oak.glb",
        species="oak",
    )
    tree = simulate(cfg)
    m = compute_metrics(tree)

    prox = m["internode_length_proximal_mean"]
    dist = m["internode_length_distal_mean"]
    assert dist < prox * 0.8, (
        f"emergent tapering not visible: proximal={prox:.4f}, distal={dist:.4f}"
    )
