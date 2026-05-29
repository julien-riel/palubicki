from pathlib import Path

import numpy as np

from palubicki.config import (
    EnvelopeConfig,
    LightConfig,
    ObstacleAABB,
    ObstacleMesh,
    ObstacleOBB,
    ObstacleSphere,
)
from palubicki.sim.light import LightGrid
from palubicki.sim.obstacles import (
    AABBObstacle,
    MeshObstacle,
    OBBObstacle,
    SphereObstacle,
)


def _grid(origin, size, resolution):
    cfg = LightConfig(grid_origin=tuple(origin), grid_size=tuple(size), grid_resolution=resolution)
    env = EnvelopeConfig()
    return LightGrid.from_config(cfg, env)


def test_voxelize_aabb_central_cells():
    grid = _grid(origin=(0, 0, 0), size=(8, 8, 8), resolution=(8, 8, 8))
    obs = AABBObstacle(ObstacleAABB(min=(2.5, 2.5, 2.5), max=(5.5, 5.5, 5.5)))
    mask = obs.voxelize(grid)
    assert mask.shape == (8, 8, 8)
    # Cells whose center lies inside [2.5, 5.5]^3; cell_size=1, so centers = i+0.5.
    # Index 2 → center 2.5 (== min, inclusive), index 5 → center 5.5 (== max, inclusive).
    # AABB.contains is inclusive on both bounds.
    expected_indices = np.array([2, 3, 4, 5])
    for i in range(8):
        for j in range(8):
            for k in range(8):
                expected = i in expected_indices and j in expected_indices and k in expected_indices
                assert bool(mask[i, j, k]) == expected, f"cell {i,j,k}"


def test_voxelize_sphere():
    grid = _grid(origin=(-4, -4, -4), size=(8, 8, 8), resolution=(8, 8, 8))
    obs = SphereObstacle(ObstacleSphere(center=(0, 0, 0), radius=2.0))
    mask = obs.voxelize(grid)
    # Voxel at the center is inside
    # Center cell: index 4 (center coord = -4 + 4.5 = 0.5, distance to origin = ~0.87 < 2)
    assert bool(mask[4, 4, 4]) is True
    # Corner cell at (0, 0, 0) → center (-3.5, -3.5, -3.5), dist ~6 → outside
    assert bool(mask[0, 0, 0]) is False


def test_voxelize_obb_identity_matches_aabb():
    grid = _grid(origin=(0, 0, 0), size=(8, 8, 8), resolution=(8, 8, 8))
    aabb = AABBObstacle(ObstacleAABB(min=(2.5, 2.5, 2.5), max=(5.5, 5.5, 5.5)))
    obb = OBBObstacle(ObstacleOBB(center=(4.0, 4.0, 4.0), half_extents=(1.5, 1.5, 1.5)))
    mask_aabb = aabb.voxelize(grid)
    mask_obb = obb.voxelize(grid)
    np.testing.assert_array_equal(mask_aabb, mask_obb)


def test_voxelize_mesh_cube():
    grid = _grid(origin=(0, 0, 0), size=(4, 4, 4), resolution=(4, 4, 4))
    obs = MeshObstacle(ObstacleMesh(
        path=Path(__file__).parent.parent / "fixtures" / "unit_cube.obj",
        translate=(1.0, 1.0, 1.0),
        scale=2.0,
    ))
    # Cube spans world (1,1,1)..(3,3,3). Voxel size = 1. Cell centers: 0.5, 1.5, 2.5, 3.5.
    # Inside cube: indices where center ∈ (1, 3), i.e. indices 1 and 2.
    mask = obs.voxelize(grid)
    assert bool(mask[1, 1, 1]) is True
    assert bool(mask[2, 2, 2]) is True
    assert bool(mask[0, 0, 0]) is False
    assert bool(mask[3, 3, 3]) is False
