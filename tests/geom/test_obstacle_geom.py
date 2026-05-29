from pathlib import Path

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


def test_build_obstacle_primitive_mesh():
    cube_path = Path(__file__).parent.parent / "fixtures" / "unit_cube.obj"
    obs = [MeshObstacle(ObstacleMesh(path=cube_path))]
    prim = build_obstacle_primitive(obs, _mat())
    assert prim.indices.shape[0] >= 12   # at least 12 triangle indices for a cube
