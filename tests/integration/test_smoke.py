# tests/integration/test_smoke.py
import pygltflib
import pytest

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
from palubicki.export.gltf import write_glb
from palubicki.geom.builder import build_mesh
from palubicki.sim.simulator import simulate

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("shape", ["sphere", "ellipsoid", "cone", "half_ellipsoid"])
def test_end_to_end_per_envelope(tmp_path, shape):
    cfg = Config(
        envelope=EnvelopeConfig(shape=shape, rx=0.5, ry=1.0, rz=0.5, marker_count=400),
        sim=SimConfig(r_perception=0.3, r_kill=0.1, shoot_extension_max=0.1, vigor_dormancy=0.5, max_simulation_years=8.0),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        seed=2,
        output=tmp_path / f"{shape}.glb",
    )
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    write_glb(mesh, cfg.output, asset_meta={"seed": cfg.seed})

    loaded = pygltflib.GLTF2().load(str(cfg.output))
    assert len(loaded.meshes) == 1
    assert loaded.meshes[0].primitives  # at least one primitive


@pytest.mark.parametrize("shape", ["sphere", "ellipsoid", "cone", "half_ellipsoid"])
def test_end_to_end_per_envelope_light_enabled(tmp_path, shape):
    cfg = Config(
        envelope=EnvelopeConfig(shape=shape, rx=0.5, ry=1.0, rz=0.5, marker_count=400),
        sim=SimConfig(r_perception=0.3, r_kill=0.1, shoot_extension_max=0.1, vigor_dormancy=0.5, max_simulation_years=6.0),
        tropism=TropismConfig(w_phototropism=0.3),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        light=LightConfig(enabled=True, grid_resolution=(16, 16, 16), n_rays=8),
        seed=3,
        output=tmp_path / f"{shape}_light.glb",
    )
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    write_glb(mesh, cfg.output, asset_meta={"seed": cfg.seed, "light_enabled": True})

    loaded = pygltflib.GLTF2().load(str(cfg.output))
    assert len(loaded.meshes) == 1
    assert loaded.meshes[0].primitives  # at least one primitive


@pytest.mark.slow
def test_smoke_forest_two_trees_with_obstacle(tmp_path):
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

    cfg = Config(
        envelope=EnvelopeConfig(marker_count=1000),
        sim=SimConfig(max_simulation_years=5.0),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "smoke.glb", seed=42,
        forest=ForestConfig(
            seeds=(
                ForestSeed(position=(0.0, 0.0, 0.0)),
                ForestSeed(position=(5.0, 0.0, 0.0)),
            ),
            obstacles=(ObstacleAABB(min=(2.0, 0.0, -1.0), max=(3.0, 1.5, 1.0)),),
        ),
    )
    forest = simulate_forest(cfg)
    write_glb_forest(forest, cfg, cfg.output, asset_meta={"seed": 42})
    assert cfg.output.exists()
    assert cfg.output.stat().st_size > 0
