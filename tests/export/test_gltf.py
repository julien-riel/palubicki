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


def test_write_glb_to_bytes_returns_glb_magic():
    from palubicki.export.gltf import write_glb_to_bytes

    mesh = Mesh(primitives=[_cube_primitive()])
    data = write_glb_to_bytes(mesh, asset_meta={"seed": 0})
    assert isinstance(data, (bytes, bytearray))
    assert bytes(data[:4]) == b"glTF"


def test_write_glb_and_to_bytes_agree(tmp_path):
    from palubicki.export.gltf import write_glb_to_bytes

    mesh = Mesh(primitives=[_cube_primitive()])
    out = tmp_path / "tree.glb"
    write_glb(mesh, out, asset_meta={"seed": 0})
    on_disk = out.read_bytes()
    in_mem = bytes(write_glb_to_bytes(mesh, asset_meta={"seed": 0}))
    assert on_disk == in_mem


def test_write_glb_to_bytes_empty_raises():
    from palubicki.export.gltf import write_glb_to_bytes

    empty = _cube_primitive()
    empty.positions = np.zeros((0, 3), dtype=np.float32)
    empty.indices = np.zeros((0,), dtype=np.uint32)
    empty.normals = np.zeros((0, 3), dtype=np.float32)
    empty.uvs = np.zeros((0, 2), dtype=np.float32)
    mesh = Mesh(primitives=[empty])
    with pytest.raises(ExportError):
        write_glb_to_bytes(mesh, asset_meta={})


def test_oversized_mesh_raises_clear_error(monkeypatch):
    """A mesh whose binary blob exceeds the GLB 4 GiB uint32 cap must raise a clear
    ExportError (not pygltflib's cryptic struct.error). Verified by shrinking the cap
    rather than building a 4 GiB mesh."""
    import palubicki.export.gltf as gltf_mod
    from palubicki.export.gltf import write_glb_to_bytes

    monkeypatch.setattr(gltf_mod, "_GLB_MAX_BYTES", 64)  # below the cube's blob size
    mesh = Mesh(primitives=[_cube_primitive()])
    with pytest.raises(ExportError, match="GLB"):
        write_glb_to_bytes(mesh, asset_meta={})


def test_triangleless_primitive_skipped_no_zero_accessor(tmp_path):
    """A primitive with vertices but no triangles (e.g. a tiny tree's bark = just the
    root-cap point) must be skipped, not emitted as a count-0 accessor (invalid glTF).
    A real primitive alongside it still exports."""
    degenerate = _cube_primitive()
    degenerate.indices = np.zeros((0,), dtype=np.uint32)  # verts but no tris
    real = _leaf_primitive()
    mesh = Mesh(primitives=[degenerate, real])
    out = tmp_path / "mixed.glb"
    write_glb(mesh, out, asset_meta={"seed": 1})
    loaded = pygltflib.GLTF2().load(str(out))
    assert len(loaded.meshes[0].primitives) == 1  # only the real one
    for acc in loaded.accessors:
        assert acc.count > 0  # no count-0 accessor survived


def test_all_triangleless_raises_empty(tmp_path):
    degenerate = _cube_primitive()
    degenerate.indices = np.zeros((0,), dtype=np.uint32)
    with pytest.raises(ExportError, match="empty"):
        write_glb(Mesh(primitives=[degenerate]), tmp_path / "e.glb", asset_meta={})


def _tinted_cube():
    prim = _cube_primitive()
    # tint rides COLOR_1 now (COLOR_0 is reserved for wind).
    prim.tint = np.tile(np.array([0.2, 0.3, 0.4], dtype=np.float32), (8, 1))
    return prim


def _wind_cube():
    prim = _cube_primitive()
    v = prim.positions.shape[0]
    prim.wind = np.tile(np.array([0.25, 0.5, 0.0], dtype=np.float32), (v, 1))
    prim.pivot = np.zeros((v, 3), dtype=np.float32)
    prim.wind_tier = np.ones((v,), dtype=np.float32)
    prim.tangents = np.tile(np.array([1.0, 0.0, 0.0, 1.0], dtype=np.float32), (v, 1))
    return prim


def test_tint_rides_color1_and_basecolor_neutralized(tmp_path):
    mesh = Mesh(primitives=[_tinted_cube()])
    out = tmp_path / "tinted.glb"
    write_glb(mesh, out, asset_meta={"seed": 1})
    loaded = pygltflib.GLTF2().load(str(out))
    prim = loaded.meshes[0].primitives[0]
    # Tint is COLOR_1; COLOR_0 stays free (no wind on this cube).
    assert getattr(prim.attributes, "COLOR_1", None) is not None
    assert prim.attributes.COLOR_0 is None
    mat = loaded.materials[prim.material]
    # tint present -> base colour neutralized so the per-vertex tint controls hue.
    assert list(mat.pbrMetallicRoughness.baseColorFactor) == [1.0, 1.0, 1.0, 1.0]


def test_no_tint_no_color1_basecolor_preserved(tmp_path):
    mesh = Mesh(primitives=[_cube_primitive()])
    out = tmp_path / "plain.glb"
    write_glb(mesh, out, asset_meta={"seed": 1})
    loaded = pygltflib.GLTF2().load(str(out))
    prim = loaded.meshes[0].primitives[0]
    assert prim.attributes.COLOR_0 is None
    assert getattr(prim.attributes, "COLOR_1", None) is None
    mat = loaded.materials[prim.material]
    # base_color preserved (0.5, 0.3, 0.1, 1.0) from _cube_primitive's material
    np.testing.assert_allclose(mat.pbrMetallicRoughness.baseColorFactor, [0.5, 0.3, 0.1, 1.0], atol=1e-6)


def test_wind_contract_channels_and_accessor_types(tmp_path):
    """The P1 portable wind contract: COLOR_0=VEC3 wind, TANGENT=VEC4, pivot split
    across TEXCOORD_1/TEXCOORD_2 (VEC2). Wind in COLOR_0 must NOT neutralize the
    base colour (that is the tint/COLOR_1 trigger)."""
    mesh = Mesh(primitives=[_wind_cube()])
    out = tmp_path / "wind.glb"
    write_glb(mesh, out, asset_meta={"seed": 1})
    loaded = pygltflib.GLTF2().load(str(out))
    prim = loaded.meshes[0].primitives[0]
    a = prim.attributes

    def _acc(name):
        idx = getattr(a, name, None)
        assert idx is not None, f"{name} missing"
        return loaded.accessors[idx]

    assert _acc("COLOR_0").type == "VEC3"
    assert _acc("TANGENT").type == "VEC4"
    assert _acc("TEXCOORD_1").type == "VEC2"
    assert _acc("TEXCOORD_2").type == "VEC2"
    assert getattr(a, "COLOR_1", None) is None  # no tint here
    # COLOR_0 is wind, not colour -> base colour is NOT neutralized.
    mat = loaded.materials[prim.material]
    np.testing.assert_allclose(mat.pbrMetallicRoughness.baseColorFactor, [0.5, 0.3, 0.1, 1.0], atol=1e-6)
