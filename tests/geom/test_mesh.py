# tests/geom/test_mesh.py
import numpy as np

from palubicki.geom.mesh import Material, Mesh, Primitive


def test_material_basic_construction():
    mat = Material(
        name="bark", base_color=(0.4, 0.2, 0.1, 1.0),
        metallic=0.0, roughness=0.9,
        base_color_texture_png=None,
        alpha_mode="OPAQUE", alpha_cutoff=0.5, double_sided=False,
    )
    assert mat.name == "bark"


def test_primitive_holds_arrays():
    mat = Material(name="m", base_color=(1, 1, 1, 1), metallic=0, roughness=1,
                   base_color_texture_png=None, alpha_mode="OPAQUE",
                   alpha_cutoff=0.5, double_sided=False)
    prim = Primitive(
        positions=np.zeros((3, 3), dtype=np.float32),
        normals=np.zeros((3, 3), dtype=np.float32),
        uvs=np.zeros((3, 2), dtype=np.float32),
        indices=np.zeros((3,), dtype=np.uint32),
        material=mat,
    )
    assert prim.positions.shape == (3, 3)


def test_mesh_holds_multiple_primitives():
    mat = Material(name="m", base_color=(1, 1, 1, 1), metallic=0, roughness=1,
                   base_color_texture_png=None, alpha_mode="OPAQUE",
                   alpha_cutoff=0.5, double_sided=False)
    p = Primitive(
        positions=np.zeros((1, 3), dtype=np.float32),
        normals=np.zeros((1, 3), dtype=np.float32),
        uvs=np.zeros((1, 2), dtype=np.float32),
        indices=np.zeros((0,), dtype=np.uint32),
        material=mat,
    )
    mesh = Mesh(primitives=[p, p])
    assert len(mesh.primitives) == 2
