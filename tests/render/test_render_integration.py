# tests/render/test_render_integration.py
"""Slow end-to-end tests: simulate → build_mesh → render. Marked `slow`."""
from pathlib import Path

import numpy as np
import pytest

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
from palubicki.export.gltf import write_glb, write_glb_forest
from palubicki.geom.builder import build_mesh
from palubicki.render import render_glb, render_mesh, save_png
from palubicki.sim.simulator import simulate, simulate_forest

pytestmark = pytest.mark.slow


def _nonbg_ratio(img: np.ndarray, bg_rgb=(255, 255, 255), tol=8) -> float:
    delta = np.abs(img[:, :, :3].astype(int) - np.array(bg_rgb)).max(axis=2)
    return float((delta > tol).mean())


def _v1_cfg(out: Path) -> Config:
    return Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=600),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, shoot_extension_max=0.1, vigor_dormancy=0.5, max_simulation_years=10.0),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        seed=7,
        output=out,
    )


def test_render_v1_ellipsoid_from_mesh(tmp_path):
    cfg = _v1_cfg(tmp_path / "v1.glb")
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    img = render_mesh(mesh, size=(400, 400))
    assert img.shape[2] == 4
    assert _nonbg_ratio(img) > 0.005


def test_render_v1_ellipsoid_glb_roundtrip(tmp_path):
    """Render via the .glb path — exercises trimesh load + _glb_to_mesh."""
    cfg = _v1_cfg(tmp_path / "v1.glb")
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    write_glb(mesh, cfg.output, asset_meta={"seed": cfg.seed})
    img = render_glb(cfg.output, size=(400, 400))
    assert img.shape[2] == 4
    assert _nonbg_ratio(img) > 0.005


def test_render_forest_glb(tmp_path):
    cfg = Config(
        envelope=EnvelopeConfig(rx=1.5, ry=2.5, rz=1.5, shape="ellipsoid", marker_count=1500),
        sim=SimConfig(max_simulation_years=6.0),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        light=LightConfig(enabled=False),
        output=tmp_path / "forest.glb",
        seed=42,
        forest=ForestConfig(
            seeds=(
                ForestSeed(position=(0.0, 0.0, 0.0)),
                ForestSeed(position=(4.0, 0.0, 0.0)),
            ),
            obstacles=(ObstacleAABB(min=(1.5, 0.0, -1.0), max=(2.5, 2.0, 1.0)),),
        ),
    )
    forest = simulate_forest(cfg)
    write_glb_forest(forest, cfg, cfg.output, asset_meta={"seed": cfg.seed})
    img = render_glb(cfg.output, size=(500, 400))
    assert img.shape[2] == 4
    assert _nonbg_ratio(img) > 0.01   # Forest is bigger → more pixels covered.


def test_render_drop_leaves_reduces_non_bg_pixels(tmp_path):
    cfg = _v1_cfg(tmp_path / "v1.glb")
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    write_glb(mesh, cfg.output, asset_meta={})
    full = render_glb(cfg.output, size=(400, 400))
    leafless = render_glb(cfg.output, size=(400, 400), drop_leaves=True)
    # Removing leaves should reduce coverage (silhouette gets sparser).
    assert _nonbg_ratio(leafless) < _nonbg_ratio(full)


def test_render_save_to_disk(tmp_path):
    cfg = _v1_cfg(tmp_path / "v1.glb")
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    img = render_mesh(mesh, size=(300, 300))
    out = tmp_path / "v1.png"
    save_png(img, out)
    assert out.exists()
    assert out.stat().st_size > 1_000
