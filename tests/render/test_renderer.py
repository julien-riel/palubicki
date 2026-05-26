# tests/render/test_renderer.py
import numpy as np
import pytest

from palubicki.geom.mesh import Material, Mesh, Primitive


def _mk_mat(rgb=(0.7, 0.4, 0.2)):
    return Material(
        name="t", base_color=(*rgb, 1.0),
        metallic=0.0, roughness=1.0,
        base_color_texture_png=None,
        alpha_mode="OPAQUE", alpha_cutoff=0.5, double_sided=False,
    )


def _mk_prim(positions, normals, indices, rgb=(0.7, 0.4, 0.2)):
    return Primitive(
        positions=np.asarray(positions, dtype=np.float32),
        normals=np.asarray(normals, dtype=np.float32),
        uvs=np.zeros((len(positions), 2), dtype=np.float32),
        indices=np.asarray(indices, dtype=np.uint32),
        material=_mk_mat(rgb),
    )


def test_flatten_concatenates_primitives():
    from palubicki.render.renderer import _flatten
    # Primitive A: 1 triangle, brown
    pA = _mk_prim(
        positions=[(0, 0, 0), (1, 0, 0), (0, 1, 0)],
        normals=[(0, 0, 1), (0, 0, 1), (0, 0, 1)],
        indices=[0, 1, 2],
        rgb=(0.7, 0.4, 0.2),
    )
    # Primitive B: 2 triangles forming a quad, green
    pB = _mk_prim(
        positions=[(2, 0, 0), (3, 0, 0), (3, 1, 0), (2, 1, 0)],
        normals=[(0, 0, 1)] * 4,
        indices=[0, 1, 2, 0, 2, 3],
        rgb=(0.3, 0.6, 0.2),
    )
    mesh = Mesh(primitives=[pA, pB])

    tri, norms, cols = _flatten(mesh)

    assert tri.shape == (3, 3, 3)             # 3 triangles, 3 verts each, 3 coords
    assert norms.shape == (3, 3)
    assert cols.shape == (3, 3)
    # First triangle = primitive A's brown
    np.testing.assert_allclose(cols[0], (0.7, 0.4, 0.2), atol=1e-6)
    # Last two = primitive B's green
    np.testing.assert_allclose(cols[1], (0.3, 0.6, 0.2), atol=1e-6)
    np.testing.assert_allclose(cols[2], (0.3, 0.6, 0.2), atol=1e-6)
    # Normals are unit-length
    lengths = np.linalg.norm(norms, axis=1)
    np.testing.assert_allclose(lengths, np.ones(3), atol=1e-5)


def test_flatten_normalizes_non_unit_input_normals():
    from palubicki.render.renderer import _flatten
    # Pass normals with length 5; expect output unit-length.
    p = _mk_prim(
        positions=[(0, 0, 0), (1, 0, 0), (0, 1, 0)],
        normals=[(5, 0, 0), (0, 5, 0), (0, 0, 5)],
        indices=[0, 1, 2],
    )
    _, norms, _ = _flatten(Mesh(primitives=[p]))
    assert np.linalg.norm(norms[0]) == pytest.approx(1.0, abs=1e-5)
