# tests/render/test_io.py
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


def _make_solid_image(w=64, h=48, rgb=(120, 60, 200)):
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., :3] = rgb
    arr[..., 3] = 255
    return arr


# ---------- save_png ----------

def test_save_png_writes_file(tmp_path):
    from palubicki.render.io import save_png
    img = _make_solid_image()
    out = tmp_path / "out.png"
    save_png(img, out)
    assert out.exists()
    loaded = np.asarray(Image.open(out).convert("RGBA"))
    np.testing.assert_array_equal(loaded, img)


def test_save_png_rejects_non_uint8(tmp_path):
    from palubicki.render.io import save_png
    img = _make_solid_image().astype(np.float32) / 255.0
    with pytest.raises(ValueError, match="uint8"):
        save_png(img, tmp_path / "x.png")


def test_save_png_rejects_wrong_shape(tmp_path):
    from palubicki.render.io import save_png
    img = np.zeros((10, 10), dtype=np.uint8)  # 2-D, not RGBA
    with pytest.raises(ValueError, match="shape"):
        save_png(img, tmp_path / "x.png")


# ---------- _glb_to_mesh ----------

def _build_tiny_glb(tmp_path: Path) -> Path:
    """Produce a real .glb from palubicki's builder, for roundtrip testing."""
    from palubicki.config import (
        Config,
        EnvelopeConfig,
        GeomConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.export.gltf import write_glb
    from palubicki.geom.builder import build_mesh
    from palubicki.sim.simulator import simulate

    cfg = Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.5, ry=1.0, rz=0.5, marker_count=200),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1, max_iterations=4),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        seed=11,
        output=tmp_path / "tiny.glb",
    )
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    write_glb(mesh, cfg.output, asset_meta={"seed": cfg.seed})
    return cfg.output


def test_glb_to_mesh_roundtrip_returns_palubicki_mesh(tmp_path):
    from palubicki.geom.mesh import Mesh
    from palubicki.render.io import _glb_to_mesh
    glb = _build_tiny_glb(tmp_path)
    mesh = _glb_to_mesh(glb)
    assert isinstance(mesh, Mesh)
    assert len(mesh.primitives) >= 1
    for p in mesh.primitives:
        assert p.positions.dtype == np.float32
        assert p.normals.shape == p.positions.shape
        assert p.indices.dtype == np.uint32
        assert len(p.material.base_color) == 4


def test_glb_to_mesh_drop_leaves_filters_green(tmp_path):
    from palubicki.render.io import _glb_to_mesh
    glb = _build_tiny_glb(tmp_path)
    with_leaves = _glb_to_mesh(glb, drop_leaves=False)
    no_leaves = _glb_to_mesh(glb, drop_leaves=True)
    # The leaf-dominant-green primitive should be gone.
    assert len(no_leaves.primitives) < len(with_leaves.primitives)


def test_glb_to_mesh_missing_path_raises(tmp_path):
    from palubicki.render import RenderError
    from palubicki.render.io import _glb_to_mesh
    with pytest.raises(RenderError, match="could not load"):
        _glb_to_mesh(tmp_path / "does-not-exist.glb")


# ---------- render_glb ----------

def test_render_glb_produces_image(tmp_path):
    from palubicki.render import render_glb
    glb = _build_tiny_glb(tmp_path)
    img = render_glb(glb, size=(200, 200))
    assert img.dtype == np.uint8
    assert img.shape[2] == 4


# ---------- vertex color roundtrip ----------

def _tinted_tri_mesh():
    from palubicki.geom.mesh import Material, Mesh, Primitive
    mat = Material(name="bark", base_color=(0.3, 0.2, 0.1, 1.0), metallic=0.0, roughness=1.0,
                   base_color_texture_png=None, alpha_mode="OPAQUE", alpha_cutoff=0.5,
                   double_sided=False)
    prim = Primitive(
        positions=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], np.float32),
        normals=np.tile([0, 0, 1], (4, 1)).astype(np.float32),
        uvs=np.zeros((4, 2), np.float32),
        indices=np.array([0, 1, 2, 1, 3, 2], np.uint32),
        material=mat,
        colors=np.array([[0.8, 0.7, 0.6]] * 4, np.float32),
    )
    return Mesh(primitives=[prim])


def test_glb_roundtrip_preserves_vertex_colors(tmp_path):
    from palubicki.export.gltf import write_glb
    from palubicki.render.io import _glb_to_mesh
    out = tmp_path / "tinted.glb"
    write_glb(_tinted_tri_mesh(), out, asset_meta={"seed": 1})
    mesh = _glb_to_mesh(out)
    cols = mesh.primitives[0].colors
    assert cols is not None
    # tint recovered (allow trimesh's 8-bit color quantization)
    np.testing.assert_allclose(cols.mean(axis=0), [0.8, 0.7, 0.6], atol=0.02)
