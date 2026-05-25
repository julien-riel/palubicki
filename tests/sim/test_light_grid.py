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


def test_rebuild_inject_internode_vertical():
    """A 1.0-length vertical internode of diameter 0.02 (radius 0.01) on cell_size 0.1
       → ~10 cells get LAI from lateral surface 2π·0.01·0.1 each."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(1.0, 1.0, 1.0),
        grid_resolution=(10, 10, 10),
        leaf_area=0.0,             # disable leaf injection for this test
        internode_area_scale=1.0,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    # Build: root at (0.5, 0.0, 0.5), tip at (0.5, 1.0, 0.5), internode is vertical
    root = Node(position=np.array([0.5, 0.0, 0.5]))
    tip = Node(position=np.array([0.5, 1.0, 0.5]))
    iod = Internode(parent_node=root, child_node=tip, length=1.0, is_main_axis=True)
    iod.diameter = 0.02   # r = 0.01
    root.children_internodes.append(iod)
    bud = Bud(position=tip.position.copy(), direction=np.array([0.0, 1.0, 0.0]), axis_order=0, parent_node=tip)
    tip.terminal_bud = bud
    tree = Tree(root=root, active_buds=[bud], all_internodes=[iod])

    grid.rebuild_from_tree(tree, cfg)

    # Vertical column at (x=5, z=5), y from 0 to 9. Each cell should have LAI > 0.
    column = grid.lai[5, :, 5]
    assert np.all(column[:10] > 0.0), f"expected all 10 cells filled, got {column[:10]}"
    # Total LAI = total lateral surface / cell_volume = (2π·0.01·1.0) / 0.001 = 62.83...
    expected_total = (2 * np.pi * 0.01 * 1.0) / (0.1 * 0.1 * 0.1)
    assert grid.lai.sum() == pytest.approx(expected_total, rel=1e-4)


def test_rebuild_internode_scaled():
    """internode_area_scale=0.5 → half the LAI from internodes."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(1.0, 1.0, 1.0),
        grid_resolution=(10, 10, 10),
        leaf_area=0.0,
        internode_area_scale=0.5,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    root = Node(position=np.array([0.5, 0.0, 0.5]))
    tip = Node(position=np.array([0.5, 1.0, 0.5]))
    iod = Internode(parent_node=root, child_node=tip, length=1.0, is_main_axis=True)
    iod.diameter = 0.02
    root.children_internodes.append(iod)
    bud = Bud(position=tip.position.copy(), direction=np.array([0.0, 1.0, 0.0]), axis_order=0, parent_node=tip)
    tip.terminal_bud = bud
    tree = Tree(root=root, active_buds=[bud], all_internodes=[iod])

    grid.rebuild_from_tree(tree, cfg)

    expected_total = 0.5 * (2 * np.pi * 0.01 * 1.0) / (0.1 * 0.1 * 0.1)
    assert grid.lai.sum() == pytest.approx(expected_total, rel=1e-4)


def test_rebuild_recomputes_radii():
    """rebuild_from_tree calls compute_radii to populate iod.diameter."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(1.0, 1.0, 1.0),
        grid_resolution=(10, 10, 10),
        leaf_area=0.0,
        internode_area_scale=1.0,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    root = Node(position=np.array([0.5, 0.0, 0.5]))
    tip = Node(position=np.array([0.5, 1.0, 0.5]))
    iod = Internode(parent_node=root, child_node=tip, length=1.0, is_main_axis=True)
    # NO pre-set diameter — let rebuild compute it.
    root.children_internodes.append(iod)
    bud = Bud(position=tip.position.copy(), direction=np.array([0.0, 1.0, 0.0]), axis_order=0, parent_node=tip)
    tip.terminal_bud = bud
    tree = Tree(root=root, active_buds=[bud], all_internodes=[iod])

    grid.rebuild_from_tree(tree, cfg, r_tip=0.005, exponent=2.0)

    # After compute_radii: tip is at r_tip=0.005, single-internode tree → iod.diameter = 0.01
    assert iod.diameter == pytest.approx(0.01)


def test_sample_transmission_empty_grid_returns_one():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    # No LAI injected at all
    T = grid.sample_transmission(np.array([5.0, 5.0, 5.0]), np.array([0.0, 1.0, 0.0]), k=0.5)
    assert T == pytest.approx(1.0)


def test_sample_transmission_uniform_lai():
    """Uniform LAI L → T(p, dir) = exp(-k * L * dist_in_grid)."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    L = 2.0
    grid.lai.fill(L)
    # Ray from (5, 0.001, 5) going up: travels ~10 units inside grid.
    k = 0.5
    T = grid.sample_transmission(np.array([5.0, 0.001, 5.0]), np.array([0.0, 1.0, 0.0]), k=k)
    expected = np.exp(-k * L * 10.0)
    assert T == pytest.approx(expected, rel=1e-2)


def test_sample_transmission_starts_outside_grid():
    """If origin is outside grid, transmission is 1.0 until the ray enters."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    grid.lai.fill(0.0)   # explicit
    T = grid.sample_transmission(np.array([-5.0, 5.0, 5.0]), np.array([1.0, 0.0, 0.0]), k=0.5)
    assert T == pytest.approx(1.0)


def test_sample_transmission_zero_direction():
    """Zero-length direction is a no-op; return 1.0."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    T = grid.sample_transmission(np.array([5.0, 5.0, 5.0]), np.array([0.0, 0.0, 0.0]), k=0.5)
    assert T == pytest.approx(1.0)


def test_sample_hemisphere_open_sky_returns_full_light():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    # Empty grid (LAI=0 everywhere) → all rays transmit fully → light_factor=1.0
    lf, grad = grid.sample_hemisphere(
        np.array([5.0, 5.0, 5.0]),
        n_rays=16,
        light_direction=np.array([0.0, 1.0, 0.0]),
        k=0.5,
        seed=42,
    )
    assert lf == pytest.approx(1.0, rel=1e-4)
    # Gradient = normalize(Σ T_k · d_k) ; with all T_k=1 and cosine-weighted dirs,
    # the sum is biased toward the light direction (y axis = up).
    np.testing.assert_allclose(grad, [0.0, 1.0, 0.0], atol=0.2)


def test_sample_hemisphere_dense_uniform_layer_attenuates():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    grid.lai.fill(1.0)
    lf, _grad = grid.sample_hemisphere(
        np.array([5.0, 0.1, 5.0]),
        n_rays=16,
        light_direction=np.array([0.0, 1.0, 0.0]),
        k=0.5,
        seed=42,
    )
    assert 0.0 < lf < 1.0   # attenuated but not zero (rays exit eventually)


def test_sample_hemisphere_deterministic_with_seed():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    grid.lai.fill(0.3)
    lf1, grad1 = grid.sample_hemisphere(np.array([5.0, 5.0, 5.0]), n_rays=16, light_direction=np.array([0.0, 1.0, 0.0]), k=0.5, seed=7)
    lf2, grad2 = grid.sample_hemisphere(np.array([5.0, 5.0, 5.0]), n_rays=16, light_direction=np.array([0.0, 1.0, 0.0]), k=0.5, seed=7)
    assert lf1 == lf2
    np.testing.assert_array_equal(grad1, grad2)


def test_sample_hemisphere_gradient_points_to_open_side():
    """Place a dense block on the -x side of the bud; gradient should point +x (away from shadow)."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(20, 10, 10),   # finer x resolution
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    # Dense LAI in the -x half
    grid.lai[:10, :, :] = 5.0
    lf, grad = grid.sample_hemisphere(
        np.array([5.0, 5.0, 5.0]),
        n_rays=64,                              # more rays for stability
        light_direction=np.array([0.0, 1.0, 0.0]),
        k=0.5,
        seed=42,
    )
    # The bud sits at x=5 which is at the boundary; rays toward +x see less LAI.
    # Gradient.x should be positive (toward open side).
    assert grad[0] > 0.0
