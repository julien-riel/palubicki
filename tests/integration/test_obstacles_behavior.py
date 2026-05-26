import numpy as np
import pytest

from palubicki.config import (
    Config, EnvelopeConfig, ForestConfig, ForestSeed, GeomConfig, LightConfig,
    ObstacleAABB, PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.sim.simulator import simulate_forest


@pytest.mark.slow
def test_obstacle_wall_deflects_crown(tmp_path):
    """A wall close to the tree → fewer internodes on the wall side than on the open side."""
    def _make_cfg(with_wall: bool):
        return Config(
            envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=4000),
            sim=SimConfig(max_iterations=15),
            tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
            output=tmp_path / "x.glb", seed=42,
            forest=ForestConfig(
                seeds=(ForestSeed(position=(0.0, 0.0, 0.0)),),
                obstacles=((ObstacleAABB(min=(1.0, 0.0, -3.0), max=(1.2, 5.0, 3.0)),) if with_wall else ()),
            ),
        )

    forest_open = simulate_forest(_make_cfg(False))
    forest_wall = simulate_forest(_make_cfg(True))

    # Count internode endpoints with x > 0.8 (wall side) vs x < -0.8 (open side)
    def _count(side_filter):
        tree = forest_wall.trees[0] if side_filter == "wall" else forest_open.trees[0]
        if side_filter == "wall":
            xs = [iod.child_node.position[0] for iod in tree.all_internodes]
            return sum(1 for x in xs if x > 0.8)
        # baseline check: open tree should have plenty of mass on the +x side
        xs = [iod.child_node.position[0] for iod in tree.all_internodes]
        return sum(1 for x in xs if x > 0.8)

    open_count = _count("open")
    wall_count = _count("wall")
    # The wall is at x=1.0–1.2 → wall side should have meaningfully fewer internodes in the wall case.
    # A ~25% reduction is observable even at moderate iteration counts.
    assert wall_count < 0.8 * open_count, f"open={open_count}, wall={wall_count}"
