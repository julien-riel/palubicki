from palubicki.config import (
    BudBreakConfig, Config, EnvelopeConfig, GeomConfig, LightConfig,
    PhyllotaxyConfig, SagConfig, SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.sim.simulator import simulate


def _minimal_config(tmp_path, bud_break_bias: BudBreakConfig) -> Config:
    return Config(
        envelope=EnvelopeConfig(rx=2.0, ry=4.0, rz=2.0, marker_count=2000),
        sim=SimConfig(
            max_iterations=12,
            internode_length=0.15,
            bud_break_bias=bud_break_bias,
        ),
        tropism=TropismConfig(w_orthotropy_main=0.5, w_orthotropy_lateral=0.0),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        light=LightConfig(),
        sag=SagConfig(),
        output=tmp_path / "out.glb",
        seed=42,
    )


def test_uniform_mode_matches_default_simulator(tmp_path):
    cfg_uniform = _minimal_config(tmp_path, BudBreakConfig(mode="uniform", strength=0.0))
    tree_a = simulate(cfg_uniform)
    cfg_basis_strength_zero = _minimal_config(
        tmp_path, BudBreakConfig(mode="basitonic", strength=0.0)
    )
    tree_b = simulate(cfg_basis_strength_zero)
    # strength=0 disables the bias regardless of mode → identical evolution.
    assert len(tree_a.all_internodes) == len(tree_b.all_internodes)


def test_basitonic_mode_changes_tree_versus_uniform(tmp_path):
    cfg_uniform = _minimal_config(tmp_path, BudBreakConfig(mode="uniform", strength=0.0))
    tree_u = simulate(cfg_uniform)
    cfg_basitonic = _minimal_config(
        tmp_path, BudBreakConfig(mode="basitonic", strength=0.9)
    )
    tree_b = simulate(cfg_basitonic)
    # Strong basitonic bias re-distributes vigor along the trunk; under these
    # settings (seed=42, 12 iterations) the resulting tree has materially
    # fewer internodes than the uniform baseline. Comparing total counts is a
    # stronger structural invariant than zip-of-lengths, which can pass on a
    # truncated shared prefix.
    assert len(tree_u.all_internodes) != len(tree_b.all_internodes)
