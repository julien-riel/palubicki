"""Verify the per-iteration update_diameters_incremental matches a one-shot
compute_radii on the final tree (pipe model is len-independent)."""
import pytest

from palubicki.config import (
    Config,
    ElongationConfig,
    EnvelopeConfig,
    GeomConfig,
    PhyllotaxyConfig,
    SheddingConfig,
    SimConfig,
    TropismConfig,
)
from palubicki.sim.simulator import simulate_forest


@pytest.mark.slow
def test_diameter_progression_final_matches_post_sim_compute_radii(tmp_path):
    from palubicki.sim.radii import compute_radii

    cfg = Config(
        envelope=EnvelopeConfig(rx=3.0, ry=4.0, rz=3.0, marker_count=2000),
        sim=SimConfig(max_iterations=15,
                      elongation=ElongationConfig(enabled=True, tau_iterations=2.0)),
        tropism=TropismConfig(w_orthotropy_main=0.3, w_phototropism=0.2),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        output=tmp_path / "tree.glb",
        seed=42,
    )
    forest = simulate_forest(cfg)
    tree = forest.trees[0]

    sim_diam = [iod.diameter for iod in tree.all_internodes]

    compute_radii(tree, r_tip=cfg.geom.r_tip, exponent=cfg.geom.pipe_exponent)
    fresh_diam = [iod.diameter for iod in tree.all_internodes]

    assert len(sim_diam) == len(fresh_diam) and len(sim_diam) > 0
    for s, f in zip(sim_diam, fresh_diam, strict=True):
        assert abs(s - f) < 1e-9
