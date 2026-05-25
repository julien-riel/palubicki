import numpy as np
import pytest

from palubicki.config import EnvelopeConfig, LightConfig
from palubicki.sim.light import LightGrid
from palubicki.sim.tree import Bud, BudState, Internode, Node, Tree


def _make_tree_with_terminal_at(pos: np.ndarray) -> Tree:
    """Tree: root → one internode → terminal bud at `pos`. No lateral buds."""
    root = Node(position=np.zeros(3))
    leaf_node = Node(position=pos)
    iod = Internode(parent_node=root, child_node=leaf_node, length=float(np.linalg.norm(pos)), is_main_axis=True)
    iod.diameter = 0.01  # avoid 0 for later tasks
    root.children_internodes.append(iod)
    bud = Bud(position=pos.copy(), direction=np.array([0.0, 1.0, 0.0]), axis_order=0, parent_node=leaf_node)
    leaf_node.terminal_bud = bud
    return Tree(root=root, active_buds=[bud], all_internodes=[iod])


def test_light_grid_explicit_bounds():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    env = EnvelopeConfig()
    grid = LightGrid.from_config(cfg, env)
    np.testing.assert_array_equal(grid.origin, np.array([0.0, 0.0, 0.0]))
    np.testing.assert_array_equal(grid.cell_size, np.array([1.0, 1.0, 1.0]))
    assert grid.resolution == (10, 10, 10)
    assert grid.lai.shape == (10, 10, 10)
    assert grid.lai.dtype == np.float32


def test_world_to_cell_basic():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    assert grid.world_to_cell(np.array([0.5, 0.5, 0.5])) == (0, 0, 0)
    assert grid.world_to_cell(np.array([5.5, 7.2, 1.1])) == (5, 7, 1)
    assert grid.world_to_cell(np.array([9.999, 9.999, 9.999])) == (9, 9, 9)


def test_world_to_cell_out_of_bounds_returns_none():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    assert grid.world_to_cell(np.array([-0.1, 0.0, 0.0])) is None
    assert grid.world_to_cell(np.array([10.1, 0.0, 0.0])) is None
    assert grid.world_to_cell(np.array([0.0, -1.0, 0.0])) is None


def test_cell_to_world_center():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    np.testing.assert_allclose(grid.cell_to_world_center(0, 0, 0), [0.5, 0.5, 0.5])
    np.testing.assert_allclose(grid.cell_to_world_center(5, 7, 1), [5.5, 7.5, 1.5])


def test_from_config_autofit_ellipsoid():
    """When origin/size are None, fit to envelope AABB with sky margin.
       AABB: [-2,2] × [-3,3] × [-2,2] → extent (4, 6, 4)
       origin = aabb_min - 0.1 * extent = (-2.4, -3.6, -2.4)
       size = (1.2*4, 1.4*6, 1.2*4) = (4.8, 8.4, 4.8)"""
    cfg = LightConfig(grid_origin=None, grid_size=None, grid_resolution=(16, 16, 16))
    env = EnvelopeConfig(shape="ellipsoid", rx=2.0, ry=3.0, rz=2.0, center=(0.0, 0.0, 0.0))
    grid = LightGrid.from_config(cfg, env)
    np.testing.assert_allclose(grid.origin, [-2.4, -3.6, -2.4], atol=1e-9)
    np.testing.assert_allclose(grid.cell_size * np.array(cfg.grid_resolution), [4.8, 8.4, 4.8], atol=1e-9)


def test_from_config_autofit_half_ellipsoid_starts_at_y_zero():
    cfg = LightConfig(grid_origin=None, grid_size=None, grid_resolution=(16, 16, 16))
    env = EnvelopeConfig(shape="half_ellipsoid", rx=2.0, ry=3.0, rz=2.0, center=(0.0, 0.0, 0.0))
    grid = LightGrid.from_config(cfg, env)
    # AABB y range [0, 3] → extent_y = 3 → origin.y = 0 - 0.1 * 3 = -0.3
    np.testing.assert_allclose(grid.origin[1], -0.3, atol=1e-9)


def test_from_config_autofit_cone():
    cfg = LightConfig(grid_origin=None, grid_size=None, grid_resolution=(16, 16, 16))
    env = EnvelopeConfig(shape="cone", rx=1.5, ry=8.0, rz=1.5, center=(0.0, 0.0, 0.0))
    grid = LightGrid.from_config(cfg, env)
    # Cone AABB: x/z in [-rx, rx]=[-1.5,1.5], y in [0, ry]=[0, 8]. extent=(3, 8, 3).
    # origin = aabb_min - 0.1 * extent = (-1.5 - 0.3, 0 - 0.8, -1.5 - 0.3) = (-1.8, -0.8, -1.8)
    np.testing.assert_allclose(grid.origin, [-1.8, -0.8, -1.8], atol=1e-9)


def test_rebuild_inject_single_leaf():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
        leaf_area=0.04,
        internode_area_scale=0.0,   # disable internode injection for this test
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))

    grid.rebuild_from_tree(tree, cfg)

    # cell_volume = 1.0 ; leaf adds 0.04 / 1.0 = 0.04 to one voxel
    assert grid.lai[5, 7, 1] == pytest.approx(0.04, rel=1e-6)
    # all other voxels are 0
    assert grid.lai.sum() == pytest.approx(0.04, rel=1e-6)


def test_rebuild_skips_dead_buds():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
        leaf_area=0.04,
        internode_area_scale=0.0,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))
    tree.active_buds[0].state = BudState.DEAD

    grid.rebuild_from_tree(tree, cfg)

    assert grid.lai.sum() == pytest.approx(0.0)


def test_rebuild_skips_non_terminal_nodes():
    """Only terminal buds (leaves) inject LAI, not lateral buds or internal nodes."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
        leaf_area=0.04,
        internode_area_scale=0.0,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))
    # Add a lateral bud at a different cell — should NOT contribute LAI
    lat = Bud(position=np.array([2.5, 3.5, 4.5]), direction=np.array([1.0, 0.0, 0.0]), axis_order=1, parent_node=tree.root)
    tree.root.lateral_buds.append(lat)
    tree.active_buds.append(lat)

    grid.rebuild_from_tree(tree, cfg)

    # Only the terminal contributes
    assert grid.lai[5, 7, 1] == pytest.approx(0.04)
    assert grid.lai[2, 3, 4] == pytest.approx(0.0)


def test_rebuild_idempotent_zeros_first():
    """Repeated rebuilds reset LAI (no accumulation across steps)."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
        leaf_area=0.04,
        internode_area_scale=0.0,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))

    grid.rebuild_from_tree(tree, cfg)
    grid.rebuild_from_tree(tree, cfg)

    assert grid.lai.sum() == pytest.approx(0.04)  # not 0.08
