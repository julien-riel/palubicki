"""Phase 2C: verify Internode captures the parent bud's light_factor."""

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
from palubicki.sim.simulator import simulate


def _base_cfg(tmp_path, *, light_enabled: bool) -> Config:
    return Config(
        envelope=EnvelopeConfig(rx=1.0, ry=2.0, rz=1.0, marker_count=400),
        sim=SimConfig(
            internode_length=0.15, max_simulation_years=4.0,
            r_perception=0.6, r_kill=0.1,
        ),
        tropism=TropismConfig(w_orthotropy_main=0.3),
        phyllotaxy=PhyllotaxyConfig(mode="alternate"),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        light=LightConfig(enabled=light_enabled, n_rays=8),
        output=tmp_path / "x.glb",
        seed=7,
    )


def test_internode_default_light_factor_one_when_no_light(tmp_path):
    cfg = _base_cfg(tmp_path, light_enabled=False)
    tree = simulate(cfg)
    assert len(tree.all_internodes) > 0
    for iod in tree.all_internodes:
        assert iod.light_factor == 1.0


def test_internode_captures_bud_light_factor(tmp_path):
    cfg = _base_cfg(tmp_path, light_enabled=True)
    tree = simulate(cfg)
    assert len(tree.all_internodes) > 0
    factors = [iod.light_factor for iod in tree.all_internodes]
    assert all(0.0 <= f <= 1.0 for f in factors)
    assert any(f < 0.999 for f in factors), (
        f"expected at least one shaded internode, got factors={factors}"
    )
