# tests/render/test_camera.py
import numpy as np
import pytest

from palubicki.geom.mesh import Material, Mesh, Primitive
from palubicki.render.camera import Camera


def _box_mesh(lo: tuple, hi: tuple) -> Mesh:
    """A two-triangle quad covering the corners (lo, hi). For testing only."""
    positions = np.array(
        [lo, (hi[0], lo[1], lo[2]), hi, (lo[0], hi[1], hi[2])],
        dtype=np.float32,
    )
    normals = np.tile(np.array([0, 0, 1], dtype=np.float32), (4, 1))
    uvs = np.zeros((4, 2), dtype=np.float32)
    indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
    mat = Material(
        name="t", base_color=(0.5, 0.5, 0.5, 1.0),
        metallic=0.0, roughness=1.0,
        base_color_texture_png=None,
        alpha_mode="OPAQUE", alpha_cutoff=0.5, double_sided=False,
    )
    return Mesh(primitives=[Primitive(
        positions=positions, normals=normals, uvs=uvs,
        indices=indices, material=mat,
    )])


def test_camera_defaults():
    cam = Camera()
    assert cam.elevation_deg == 20.0
    assert cam.azimuth_deg == 35.0
    assert cam.target == (0.0, 0.0, 0.0)
    assert cam.distance is None
    assert cam.margin == 0.08


def test_camera_fit_centers_target_on_bbox():
    mesh = _box_mesh(lo=(-1.0, -1.0, -1.0), hi=(2.0, 2.0, 2.0))
    cam = Camera.fit(mesh)
    np.testing.assert_allclose(cam.target, (0.5, 0.5, 0.5), atol=1e-6)


def test_camera_fit_distance_scales_with_extent():
    small = Camera.fit(_box_mesh((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5)))
    big = Camera.fit(_box_mesh((-5.0, -5.0, -5.0), (5.0, 5.0, 5.0)))
    assert big.distance > small.distance
    assert big.distance / small.distance == pytest.approx(10.0, rel=0.05)


def test_camera_fit_accepts_overrides():
    mesh = _box_mesh((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0))
    cam = Camera.fit(mesh, elevation_deg=45.0, azimuth_deg=90.0)
    assert cam.elevation_deg == 45.0
    assert cam.azimuth_deg == 90.0


def test_camera_fit_empty_mesh_raises():
    from palubicki.render import RenderError
    empty = Mesh(primitives=[])
    with pytest.raises(RenderError, match="empty"):
        Camera.fit(empty)
