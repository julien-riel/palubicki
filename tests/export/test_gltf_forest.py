
import pygltflib

from palubicki.config import (
    Config,
    EnvelopeConfig,
    ForestConfig,
    ForestSeed,
    GeomConfig,
    LightConfig,
    ObstacleAABB,
    PhyllotaxyConfig,
    SheddingConfig,
    SimConfig,
    TropismConfig,
)
from palubicki.export.gltf import write_glb_forest
from palubicki.sim.simulator import simulate_forest


def test_write_glb_forest_has_one_node_per_tree(tmp_path):
    cfg = Config(
        envelope=EnvelopeConfig(rx=2, ry=3, rz=2, marker_count=1500),
        sim=SimConfig(max_simulation_years=4.0),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "scene.glb", seed=42,
        forest=ForestConfig(seeds=(
            ForestSeed(position=(0.0, 0.0, 0.0)),
            ForestSeed(position=(8.0, 0.0, 0.0)),
        )),
    )
    forest = simulate_forest(cfg)
    write_glb_forest(forest, cfg, tmp_path / "scene.glb", asset_meta={"seed": 42})

    loaded = pygltflib.GLTF2().load(str(tmp_path / "scene.glb"))
    names = [n.name for n in loaded.nodes]
    assert "tree_0" in names
    assert "tree_1" in names


def test_write_glb_forest_includes_obstacles_node(tmp_path):
    cfg = Config(
        envelope=EnvelopeConfig(rx=2, ry=3, rz=2, marker_count=1500),
        sim=SimConfig(max_simulation_years=4.0),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "scene.glb", seed=42,
        forest=ForestConfig(
            seeds=(ForestSeed(position=(0.0, 0.0, 0.0)),),
            obstacles=(ObstacleAABB(min=(3, 0, -1), max=(4, 2, 1)),),
            export_obstacles_geometry=True,
        ),
    )
    forest = simulate_forest(cfg)
    write_glb_forest(forest, cfg, tmp_path / "scene.glb", asset_meta={"seed": 42})

    loaded = pygltflib.GLTF2().load(str(tmp_path / "scene.glb"))
    names = [n.name for n in loaded.nodes]
    assert "obstacles" in names


def test_write_glb_forest_embeds_config_in_asset_extras(tmp_path):
    cfg = Config(
        envelope=EnvelopeConfig(rx=2, ry=3, rz=2, marker_count=1500),
        sim=SimConfig(max_simulation_years=4.0),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "scene.glb", seed=42,
        forest=ForestConfig(seeds=(ForestSeed(position=(0.0, 0.0, 0.0)),)),
    )
    forest = simulate_forest(cfg)
    write_glb_forest(
        forest, cfg, tmp_path / "scene.glb",
        asset_meta={"seed": 42, "config": {"forest": {"seeds": [{"position": [0, 0, 0]}]}}},
    )

    loaded = pygltflib.GLTF2().load(str(tmp_path / "scene.glb"))
    extras = loaded.asset.extras or {}
    assert "config" in extras
