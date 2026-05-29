
from palubicki.config import (
    Config,
    EnvelopeConfig,
    GeomConfig,
    PhyllotaxyConfig,
    SheddingConfig,
    SimConfig,
    TropismConfig,
)
from palubicki.geom.builder import build_mesh
from palubicki.sim.simulator import simulate


def _cfg(tmp_path, enable_leaves=True):
    return Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.5, ry=1.0, rz=0.5, marker_count=300),
        sim=SimConfig(r_perception=0.3, r_kill=0.1, internode_length=0.1, max_iterations=6),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(enable_leaves=enable_leaves),
        seed=1,
        output=tmp_path / "out.glb",
    )


def test_mesh_has_two_primitives_when_leaves_on(tmp_path):
    cfg = _cfg(tmp_path)
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    assert len(mesh.primitives) == 2
    assert mesh.primitives[0].material.name == "bark"
    assert mesh.primitives[1].material.name == "leaf"


def test_mesh_one_primitive_when_leaves_off(tmp_path):
    cfg = _cfg(tmp_path, enable_leaves=False)
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    assert len(mesh.primitives) == 1
    assert mesh.primitives[0].material.name == "bark"


def test_bark_has_positions(tmp_path):
    cfg = _cfg(tmp_path)
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    assert mesh.primitives[0].positions.shape[0] > 0


def test_build_mesh_applies_flare_from_config():
    import numpy as np

    def cfg(factor):
        return Config(
            envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=400),
            sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1, max_iterations=8),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(enabled=False),
            geom=GeomConfig(root_flare_factor=factor, root_flare_height=0.5, root_flare_variation=0.0),
            seed=7,
        )

    tree = simulate(cfg(1.0))
    flat = build_mesh(tree, cfg(1.0)).primitives[0].positions
    flared = build_mesh(tree, cfg(2.0)).primitives[0].positions
    # flaring the base must move at least some bark vertices outward
    assert not np.array_equal(flat, flared)
