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
    """Two trees close together → the inner-facing sides have fewer internodes than the outer-facing sides.

    Cross-tree marker depletion suppresses inner-side growth, so the outer side
    accumulates more internodes. With Phase 1 defaults (lateral orthotropy/gravi
    weights from TropismConfig), the asymmetry needs enough iterations and tight
    enough spacing to be discriminating: spacing=1.2 (inner gap=2.4, env_rx=1.5
    → envelopes overlap) and max_simulation_years=18 surface a clear outer-favored
    margin without being overly slow.

    shoot_extension_max is pinned to 0.1 here so trees stay within their own
    envelopes. With the #20 vigor model's default (0.3), main axes saturate near
    0.3 and grow clear across the midline into the neighbor's home half — then the
    half-space inner/outer classification below counts invading internodes as
    "inner" and swamps the genuine cross-tree depletion signal. At 0.1 the trees
    stay contained and the marker-depletion asymmetry (the thing under test) is
    measured cleanly. vigor_dormancy=0.5 keeps the EMA-warmup from starving growth.
    """
    cfg = Config(
        envelope=EnvelopeConfig(rx=1.5, ry=3.0, rz=1.5, marker_count=3000),
        sim=SimConfig(max_simulation_years=18.0, shoot_extension_max=0.1, vigor_dormancy=0.5),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "x.glb", seed=42,
        forest=ForestConfig(seeds=(
            ForestSeed(position=(-1.2, 0.0, 0.0)),
            ForestSeed(position=(1.2, 0.0, 0.0)),
        )),
    )
    forest = simulate_forest(cfg)

    tree_left = forest.trees[0]
    # tree_left at x=-1.2; inner side = +x (towards 0), outer side = -x
    left_inner = sum(1 for iod in tree_left.all_internodes if iod.child_node.position[0] > -1.2)
    left_outer = sum(1 for iod in tree_left.all_internodes if iod.child_node.position[0] < -1.2)
    # Outer should outgrow inner because cross-tree markers above the OTHER tree
    # get consumed by both trees, depleting the inner side faster. Margin of 5
    # restored (was widened to 15 to mask a semantic inversion under the old
    # iter=12, spacing=1.5 config).
    assert left_outer >= left_inner + 5, f"left_inner={left_inner}, left_outer={left_outer}"


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
