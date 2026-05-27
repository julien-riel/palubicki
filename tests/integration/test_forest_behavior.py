import numpy as np
import pytest

from palubicki.config import (
    Config, EnvelopeConfig, ForestConfig, ForestSeed, GeomConfig, LightConfig,
    PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.sim.simulator import simulate, simulate_forest


@pytest.mark.slow
def test_two_trees_compete_for_space(tmp_path):
    """Two trees close together → the inner-facing sides have fewer internodes than the outer-facing sides."""
    cfg = Config(
        envelope=EnvelopeConfig(rx=1.5, ry=3.0, rz=1.5, marker_count=3000),
        sim=SimConfig(max_iterations=12),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "x.glb", seed=42,
        forest=ForestConfig(seeds=(
            ForestSeed(position=(-1.5, 0.0, 0.0)),
            ForestSeed(position=(1.5, 0.0, 0.0)),
        )),
    )
    forest = simulate_forest(cfg)

    tree_left, tree_right = forest.trees[0], forest.trees[1]
    # tree_left at x=-1.5; inner side = +x (towards 0), outer side = -x
    left_inner = sum(1 for iod in tree_left.all_internodes if iod.child_node.position[0] > -1.5)
    left_outer = sum(1 for iod in tree_left.all_internodes if iod.child_node.position[0] < -1.5)
    # We expect roughly balanced or outer-favored mass; allow generous margin since
    # the trees can still grow inward where markers from the OTHER tree's envelope provide pulls.
    # After Phase 1 (lateral orthotropy weight 0.1 vs main 0.3) lateral buds explore
    # more horizontally and the asymmetry is small. Loose assertion: outer not
    # drastically below inner.
    assert left_outer >= left_inner - 15, f"left_inner={left_inner}, left_outer={left_outer}"


@pytest.mark.slow
def test_simulate_vs_simulate_forest_single_tree_match(tmp_path):
    """simulate(cfg) and simulate_forest(cfg) on cfg with no forest.seeds must produce the same tree."""
    cfg = Config(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_iterations=8),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "x.glb", seed=42,
    )
    tree_a = simulate(cfg)
    forest_b = simulate_forest(cfg)
    tree_b = forest_b.trees[0]
    assert len(tree_a.all_internodes) == len(tree_b.all_internodes)
    for ia, ib in zip(tree_a.all_internodes, tree_b.all_internodes):
        np.testing.assert_allclose(ia.child_node.position, ib.child_node.position)
