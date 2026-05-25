import numpy as np
import pygltflib
import pytest

from palubicki.export.gltf import ExportError, write_glb
from palubicki.geom.mesh import Material, Mesh, Primitive


def _cube_primitive():
    positions = np.array([
        [-0.5, -0.5, -0.5], [0.5, -0.5, -0.5], [0.5, 0.5, -0.5], [-0.5, 0.5, -0.5],
        [-0.5, -0.5,  0.5], [0.5, -0.5,  0.5], [0.5, 0.5,  0.5], [-0.5, 0.5,  0.5],
    ], dtype=np.float32)
    normals = positions / np.linalg.norm(positions, axis=1, keepdims=True)
    normals = normals.astype(np.float32)
    uvs = np.zeros((8, 2), dtype=np.float32)
    indices = np.array([
        0, 1, 2, 0, 2, 3,
        4, 6, 5, 4, 7, 6,
        0, 4, 5, 0, 5, 1,
        1, 5, 6, 1, 6, 2,
        2, 6, 7, 2, 7, 3,
        3, 7, 4, 3, 4, 0,
    ], dtype=np.uint32)
    mat = Material(
        name="bark", base_color=(0.5, 0.3, 0.1, 1.0),
        metallic=0.0, roughness=0.9, base_color_texture_png=None,
        alpha_mode="OPAQUE", alpha_cutoff=0.5, double_sided=False,
    )
    return Primitive(positions=positions, normals=normals, uvs=uvs, indices=indices, material=mat)


def _leaf_primitive():
    positions = np.array([
        [-0.05, 0.0, 0.0], [0.05, 0.0, 0.0], [0.05, 0.1, 0.0], [-0.05, 0.1, 0.0],
    ], dtype=np.float32)
    normals = np.tile(np.array([0, 0, 1], dtype=np.float32), (4, 1))
    uvs = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
    indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    mat = Material(
        name="leaf", base_color=(0.4, 0.6, 0.2, 1.0),
        metallic=0.0, roughness=0.85, base_color_texture_png=png,
        alpha_mode="MASK", alpha_cutoff=0.5, double_sided=True,
    )
    return Primitive(positions=positions, normals=normals, uvs=uvs, indices=indices, material=mat)


def test_writes_glb_file(tmp_path):
    mesh = Mesh(primitives=[_cube_primitive()])
    out = tmp_path / "cube.glb"
    write_glb(mesh, out, asset_meta={"seed": 1})
    assert out.exists()
    assert out.stat().st_size > 100


def test_roundtrip_vertex_and_index_counts(tmp_path):
    mesh = Mesh(primitives=[_cube_primitive(), _leaf_primitive()])
    out = tmp_path / "two.glb"
    write_glb(mesh, out, asset_meta={"seed": 7})
    loaded = pygltflib.GLTF2().load(str(out))
    assert len(loaded.meshes) == 1
    assert len(loaded.meshes[0].primitives) == 2


def test_asset_extras_preserved(tmp_path):
    mesh = Mesh(primitives=[_cube_primitive()])
    out = tmp_path / "meta.glb"
    write_glb(mesh, out, asset_meta={"seed": 42, "envelope": "ellipsoid"})
    loaded = pygltflib.GLTF2().load(str(out))
    extras = loaded.asset.extras or {}
    assert extras.get("seed") == 42
    assert extras.get("envelope") == "ellipsoid"


def test_empty_mesh_raises(tmp_path):
    empty = _cube_primitive()
    empty.positions = np.zeros((0, 3), dtype=np.float32)
    empty.indices = np.zeros((0,), dtype=np.uint32)
    empty.normals = np.zeros((0, 3), dtype=np.float32)
    empty.uvs = np.zeros((0, 2), dtype=np.float32)
    mesh = Mesh(primitives=[empty])
    with pytest.raises(ExportError, match="empty"):
        write_glb(mesh, tmp_path / "empty.glb", asset_meta={})
