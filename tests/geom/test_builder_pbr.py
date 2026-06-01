"""Builder wiring for the P2 photoreal master: PBR maps, hero blade, seasons."""
import numpy as np

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


def _cfg(tmp_path, **geom):
    return Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.5, ry=1.0, rz=0.5, marker_count=300),
        sim=SimConfig(r_perception=0.3, r_kill=0.1, shoot_extension_max=0.1,
                      vigor_dormancy=0.5, max_simulation_years=6.0),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(**geom), seed=1, output=tmp_path / "out.glb",
    )


def _by_name(mesh, name):
    return next(p for p in mesh.primitives if p.material.name == name)


def test_default_master_has_leaf_pbr_maps(tmp_path):
    mesh = build_mesh(simulate(_cfg(tmp_path)), _cfg(tmp_path))
    leaf = _by_name(mesh, "leaf").material
    assert leaf.normal_texture_png is not None
    assert leaf.orm_texture_png is not None
    assert leaf.transmission_texture_png is not None
    assert leaf.specular_factor and leaf.diffuse_transmission_factor > 0.0


def test_proc_bark_gets_normal_and_orm(tmp_path):
    cfg = _cfg(tmp_path, bark_texture="proc:oak_bark")
    bark = _by_name(build_mesh(simulate(cfg), cfg), "bark").material
    assert bark.normal_texture_png is not None
    assert bark.orm_texture_png is not None
    assert bark.specular_factor == 0.2


def test_no_pbr_maps_when_disabled(tmp_path):
    cfg = _cfg(tmp_path, bark_texture="proc:oak_bark", enable_pbr_maps=False)
    mesh = build_mesh(simulate(cfg), cfg)
    bark = _by_name(mesh, "bark").material
    leaf = _by_name(mesh, "leaf").material
    assert bark.normal_texture_png is None and bark.orm_texture_png is None
    assert leaf.normal_texture_png is None and leaf.transmission_texture_png is None
    assert bark.specular_factor is None and leaf.specular_factor is None


def test_hero_blade_changes_leaf_geometry(tmp_path):
    flat = build_mesh(simulate(_cfg(tmp_path)), _cfg(tmp_path))
    cfg_h = _cfg(tmp_path, leaf_blade_fold_deg=15.0, leaf_blade_curl=0.12)
    hero = build_mesh(simulate(cfg_h), cfg_h)
    fp, hp = _by_name(flat, "leaf"), _by_name(hero, "leaf")
    assert fp.positions.shape == hp.positions.shape  # same topology
    assert not np.allclose(fp.positions, hp.positions)  # displaced out of plane
    # Flat leaves carry one constant normal per blade; the hero blade does not.
    assert not np.allclose(hp.normals, hp.normals[0], atol=1e-3)


def test_hero_blade_world_tangent_orthogonal_under_splay(tmp_path):
    """Splay shears the leaf basis (bu·bv = sin(splay) ≠ 0); the lifted hero-blade
    TANGENT must still be ⟂ NORMAL so the exported TBN is square (the local-frame
    test alone misses this — orthogonality is lost only after the world lift)."""
    cfg = _cfg(tmp_path, leaf_blade_fold_deg=15.0, leaf_blade_curl=0.12, leaf_splay_deg=30.0)
    leaf = _by_name(build_mesh(simulate(cfg), cfg), "leaf")
    n = leaf.normals.astype(float)
    t = leaf.tangents[:, :3].astype(float)
    assert np.max(np.abs(np.sum(n * t, axis=1))) < 1e-4   # T ⟂ N in world space
    assert np.allclose(np.linalg.norm(t, axis=1), 1.0, atol=1e-4)
    assert set(np.unique(np.round(leaf.tangents[:, 3]))) <= {-1.0, 1.0}


def test_season_variants_attached(tmp_path):
    cfg = _cfg(tmp_path, leaf_season_variants=True, leaf_autumn_color=(0.8, 0.45, 0.1))
    leaf = _by_name(build_mesh(simulate(cfg), cfg), "leaf")
    assert leaf.material_variants is not None
    names = [n for n, _ in leaf.material_variants]
    assert names == ["summer", "autumn"]
    assert leaf.material_variants[1][1].base_color[:3] == (0.8, 0.45, 0.1)
