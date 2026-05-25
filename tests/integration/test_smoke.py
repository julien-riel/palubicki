# tests/integration/test_smoke.py
import numpy as np
import pygltflib
import pytest

from palubicki.config import (
    Config, EnvelopeConfig, GeomConfig, PhyllotaxyConfig,
    SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.export.gltf import write_glb
from palubicki.geom.builder import build_mesh
from palubicki.sim.simulator import simulate


pytestmark = pytest.mark.slow


@pytest.mark.parametrize("shape", ["sphere", "ellipsoid", "cone", "half_ellipsoid"])
def test_end_to_end_per_envelope(tmp_path, shape):
    cfg = Config(
        envelope=EnvelopeConfig(shape=shape, rx=0.5, ry=1.0, rz=0.5, marker_count=400),
        sim=SimConfig(r_perception=0.3, r_kill=0.1, internode_length=0.1, max_iterations=8),
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
