import numpy as np
import pytest

from palubicki.config import (
    Config,
    EnvelopeConfig,
    ForestConfig,
    ForestSeed,
    GeomConfig,
    LightConfig,
    PhyllotaxyConfig,
    SheddingConfig,
    SimConfig,
    TropismConfig,
)
from palubicki.sim.simulator import simulate, simulate_forest


@pytest.mark.slow
def test_two_trees_compete_for_space(tmp_path):
    """A neighbor suppresses a tree's inner-facing side more than its outer side.

    Cross-tree marker depletion (crown shyness): when two crowns' envelopes overlap,
    the contested inner region holds *one* envelope's worth of markers (uniform union
    density, #41) split between both trees by closest-bud competition, so each tree's
    inner side is starved relative to growing alone. The outer side, away from the
    neighbor, is barely touched.

    The measurement is a **lone-baseline-controlled differential**, not a raw
    inner-vs-outer count: a single tree has a large intrinsic phyllotactic asymmetry
    (here the inner half-space happens to carry ~120 more internodes than the outer
    even with NO neighbor), which dwarfs and would mask the cross-tree effect. So we
    grow the same left tree twice — alone and with a neighbor — and compare how much
    each side *loses* to the neighbor. Inner should lose far more than outer.

    shoot_extension_max is pinned to 0.1 so trees stay within their own envelopes;
    with the #20 vigor default (0.3) main axes saturate near 0.3 and grow clear
    across the midline into the neighbor's home half, polluting the half-space
    classification. vigor_dormancy=0.5 keeps the EMA-warmup from starving growth.
    """
    def _cfg(seeds):
        return Config(
            envelope=EnvelopeConfig(rx=1.5, ry=3.0, rz=1.5, marker_count=3000),
            sim=SimConfig(max_simulation_years=18.0, shoot_extension_max=0.1, vigor_dormancy=0.5),
            tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
            output=tmp_path / "x.glb", seed=42,
            forest=ForestConfig(seeds=tuple(ForestSeed(position=p) for p in seeds)),
        )

    # tree_left sits at x=-1.2; inner side = +x (towards midline), outer side = -x.
    def _split(tree):
        inner = sum(1 for iod in tree.all_internodes if iod.child_node.position[0] > -1.2)
        outer = sum(1 for iod in tree.all_internodes if iod.child_node.position[0] < -1.2)
        return inner, outer

    # Same left tree (seed 42, env centered at -1.2), grown alone vs. with a neighbor
    # at +1.2 (inner gap 2.4 < 2*env_rx=3.0 → envelopes overlap).
    lone_inner, lone_outer = _split(simulate_forest(_cfg([(-1.2, 0.0, 0.0)])).trees[0])
    pair = simulate_forest(_cfg([(-1.2, 0.0, 0.0), (1.2, 0.0, 0.0)])).trees[0]
    pair_inner, pair_outer = _split(pair)

    d_inner = pair_inner - lone_inner  # change vs. lone baseline (expected: strongly negative)
    d_outer = pair_outer - lone_outer  # (expected: near zero)
    # The neighbor must depress the inner side, and depress it markedly more than the
    # outer side. Measured at this config: d_inner=-84, d_outer=-5 (margin 79); 30 is a
    # robust floor that still discriminates the depletion signal from noise.
    assert d_inner < 0, f"inner not suppressed by neighbor: d_inner={d_inner}"
    assert d_outer - d_inner >= 30, (
        f"inner side not preferentially depleted: d_inner={d_inner}, d_outer={d_outer} "
        f"(lone={lone_inner}/{lone_outer}, pair={pair_inner}/{pair_outer})"
    )


@pytest.mark.slow
def test_simulate_vs_simulate_forest_single_tree_match(tmp_path):
    """simulate(cfg) and simulate_forest(cfg) on cfg with no forest.seeds must produce the same tree."""
    cfg = Config(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_simulation_years=8.0),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "x.glb", seed=42,
    )
    tree_a = simulate(cfg)
    forest_b = simulate_forest(cfg)
    tree_b = forest_b.trees[0]
    assert len(tree_a.all_internodes) == len(tree_b.all_internodes)
    for ia, ib in zip(tree_a.all_internodes, tree_b.all_internodes, strict=True):
        np.testing.assert_allclose(ia.child_node.position, ib.child_node.position)
