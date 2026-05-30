from pathlib import Path

import numpy as np

from palubicki.config import (
    ObstacleAABB,
    ObstacleMesh,
    ObstacleSphere,
)
from palubicki.geom.mesh import Material
from palubicki.geom.obstacle_geom import build_obstacle_primitive
from palubicki.sim.obstacles import (
    AABBObstacle,
    MeshObstacle,
    SphereObstacle,
)


def _mat():
    return Material(
        name="obstacle", base_color=(0.5, 0.5, 0.55, 0.3),
        metallic=0.0, roughness=0.9, base_color_texture_png=None,
        alpha_mode="BLEND", alpha_cutoff=0.5, double_sided=True,
    )


def test_build_obstacle_primitive_aabb():
    obs = [AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)))]
    prim = build_obstacle_primitive(obs, _mat())
    assert prim.positions.shape[1] == 3
    assert prim.indices.shape[0] % 3 == 0
    # 12 triangles for a cube = 36 indices
    assert prim.indices.shape[0] == 36


def test_build_obstacle_primitive_sphere():
    obs = [SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=1.0))]
    prim = build_obstacle_primitive(obs, _mat())
    # UV sphere at (16, 8) lat/long: triangles = 2 * 16 * 8 = 256 → 768 indices
    assert prim.indices.shape[0] > 0
    assert prim.positions.shape[0] > 0


def test_build_obstacle_primitive_combines_multiple():
    obs = [
        AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1))),
        SphereObstacle(ObstacleSphere(center=(5, 0, 0), radius=1.0)),
    ]
    prim = build_obstacle_primitive(obs, _mat())
    # Indices = AABB(36) + sphere(>0)
    assert prim.indices.shape[0] > 36


def test_build_obstacle_primitive_empty_returns_none():
    out = build_obstacle_primitive([], _mat())
    assert out is None


def _winding_dots(prim):
    """Per-triangle ``cross(v1-v0, v2-v0) · mean_vertex_normal`` (see test_tubes).

    Returns ``(dots, areas)`` where ``areas`` is the geometric-normal magnitude
    (∝ triangle area). Degenerate triangles (≈0 area — e.g. UV-sphere pole fans)
    have undefined winding; callers filter them out.
    """
    pos = np.asarray(prim.positions, dtype=np.float64)
    nor = np.asarray(prim.normals, dtype=np.float64)
    tris = np.asarray(prim.indices, dtype=np.int64).reshape(-1, 3)
    geo = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
    stored = (nor[tris[:, 0]] + nor[tris[:, 1]] + nor[tris[:, 2]]) / 3.0
    return np.einsum("ij,ij->i", geo, stored), np.linalg.norm(geo, axis=1)


def test_box_winding_agrees_with_normals():
    """Box faces must wind CCW-from-outside (glTF 2.0 §3.7.2). Regression for #33."""
    obs = [AABBObstacle(ObstacleAABB(min=(0, 0, 0), max=(1, 1, 1)))]
    prim = build_obstacle_primitive(obs, _mat())
    dots, _ = _winding_dots(prim)
    assert np.all(dots > 0), f"{int((dots <= 0).sum())} of {dots.size} box triangles wound inward"


def test_sphere_winding_agrees_with_normals():
    """UV-sphere faces must wind CCW-from-outside (glTF 2.0 §3.7.2). Regression for #33.

    Pole-fan triangles are degenerate (zero area) so their winding is undefined;
    only non-degenerate faces are checked. The original all-inward bug wound every
    non-degenerate face the wrong way, so this still catches it."""
    obs = [SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=1.0))]
    prim = build_obstacle_primitive(obs, _mat())
    dots, areas = _winding_dots(prim)
    real = areas > 1e-9
    assert real.sum() > 0
    bad = dots[real] <= 0
    assert not bad.any(), f"{int(bad.sum())} of {int(real.sum())} sphere triangles wound inward"


def test_build_obstacle_primitive_mesh():
    cube_path = Path(__file__).parent.parent / "fixtures" / "unit_cube.obj"
    obs = [MeshObstacle(ObstacleMesh(path=cube_path))]
    prim = build_obstacle_primitive(obs, _mat())
    assert prim.indices.shape[0] >= 12   # at least 12 triangle indices for a cube
