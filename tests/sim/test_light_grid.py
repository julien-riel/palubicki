import numpy as np
import pytest

from palubicki.config import EnvelopeConfig, GeomConfig, LightConfig
from palubicki.sim.light import LightGrid
from palubicki.sim.tree import Bud, BudState, Internode, Leaf, Node, Tree

# Default foliage params used by the leaf-injection tests. Real per-leaf blade
# area (#62) now drives the LAI deposit, so the tests need a concrete GeomConfig
# to compute the expected occluding area from.
_GEOM = GeomConfig()


def _leaf_area_at(tree: Tree, geom: GeomConfig = _GEOM) -> float:
    """Expected total occluding area the grid should deposit for `tree`.

    Sourced from the same shared helper the deposit uses; the rendered-geometry
    cross-check lives in tests/sim/test_diagnostics.py, so here we exercise
    placement + summation, not the area formula itself."""
    from palubicki.geom.leaves import leaf_area_records

    return float(sum(area for _pos, area in leaf_area_records(tree, geom)))


def _make_tree_with_terminal_at(pos: np.ndarray, *, with_leaf: bool = True) -> Tree:
    """Tree: root → one internode → terminal bud at `pos`. No lateral buds.

    `with_leaf` seats one ACTIVE Leaf on the terminal node so the real-leaf-area
    LAI deposit (#62) has foliage to read."""
    root = Node(position=np.zeros(3))
    leaf_node = Node(position=pos)
    iod = Internode(parent_node=root, child_node=leaf_node, length=float(np.linalg.norm(pos)), is_main_axis=True)
    iod.diameter = 0.01  # avoid 0 for later tasks
    root.children_internodes.append(iod)
    bud = Bud(position=pos.copy(), direction=np.array([0.0, 1.0, 0.0]), axis_order=0, parent_node=leaf_node)
    leaf_node.terminal_bud = bud
    if with_leaf:
        leaf_node.leaves.append(Leaf(parent_node=leaf_node, azimuth=0.0, birth_time=0.0))
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
        internode_area_scale=0.0,   # disable internode injection for this test
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))

    grid.rebuild_from_tree(tree, cfg, geom=_GEOM)

    # cell_volume = 1.0 ; the one leaf deposits its real blade area into one voxel.
    expected = _leaf_area_at(tree)  # / cell_volume == 1.0
    assert expected > 0.0
    assert grid.lai[5, 7, 1] == pytest.approx(expected, rel=1e-6)
    # all other voxels are 0
    assert grid.lai.sum() == pytest.approx(expected, rel=1e-6)


def test_rebuild_skips_dead_buds():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
        internode_area_scale=0.0,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))
    tree.active_buds[0].state = BudState.DEAD

    grid.rebuild_from_tree(tree, cfg, geom=_GEOM)

    # A dead apex is not a leaf-bearing node → its foliage is not deposited.
    assert grid.lai.sum() == pytest.approx(0.0)


def test_rebuild_skips_non_terminal_nodes():
    """Only leaf-bearing apex nodes inject LAI, not lateral buds or internal nodes."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
        internode_area_scale=0.0,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))
    # Add a lateral bud at a different cell — should NOT contribute LAI
    lat = Bud(position=np.array([2.5, 3.5, 4.5]), direction=np.array([1.0, 0.0, 0.0]), axis_order=1, parent_node=tree.root)
    tree.root.lateral_buds.append(lat)
    tree.active_buds.append(lat)

    grid.rebuild_from_tree(tree, cfg, geom=_GEOM)

    # Only the terminal leaf contributes
    expected = _leaf_area_at(tree)
    assert grid.lai[5, 7, 1] == pytest.approx(expected)
    assert grid.lai[2, 3, 4] == pytest.approx(0.0)


def test_rebuild_idempotent_zeros_first():
    """Repeated rebuilds reset LAI (no accumulation across steps)."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
        internode_area_scale=0.0,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))

    grid.rebuild_from_tree(tree, cfg, geom=_GEOM)
    grid.rebuild_from_tree(tree, cfg, geom=_GEOM)

    expected = _leaf_area_at(tree)
    assert grid.lai.sum() == pytest.approx(expected)  # not 2×


def test_blade_morphology_changes_lai_deposit():
    """Acceptance #62: identical skeleton + different broadleaf blade morphology ⇒
    measurably different self-shading. The deposit is the real blade area, so a big
    broad palmate blade occludes substantially more than a small narrow one."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
        internode_area_scale=0.0,
    )
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))

    small = GeomConfig(leaf_size=0.05, leaf_shape="elliptic", leaf_aspect=0.3)
    large = GeomConfig(leaf_size=0.12, leaf_shape="palmate", leaf_aspect=1.0)

    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    grid.rebuild_from_tree(tree, cfg, geom=small)
    lai_small = grid.lai.sum()

    grid.rebuild_from_tree(tree, cfg, geom=large)
    lai_large = grid.lai.sum()

    assert lai_small > 0.0
    # Broad palmate at 0.12 must occlude substantially more than a small narrow blade at 0.05.
    assert lai_large > 2.0 * lai_small


def test_needle_path_uses_real_needle_area():
    """#7: conifers (leaf_shape == 'linear') now deposit the *real* per-needle blade
    area (leaf_area_records — the same area the .glb and total_leaf_area use), scaled
    by light.needle_area_scale. This replaces the legacy terminal-bud scalar canopy
    shell, so — unlike the old scalar — the deposit IS sensitive to leaf_size, and
    needle_area_scale is a linear multiplier (0 opts out)."""
    base = {"grid_origin": (0.0, 0.0, 0.0), "grid_size": (10.0, 10.0, 10.0),
            "grid_resolution": (10, 10, 10), "internode_area_scale": 0.0}
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))

    small = GeomConfig(leaf_shape="linear", leaf_size=0.05)
    big = GeomConfig(leaf_shape="linear", leaf_size=0.20)

    g_small = LightGrid.from_config(LightConfig(**base, needle_area_scale=1.0), EnvelopeConfig())
    g_small.rebuild_from_tree(tree, LightConfig(**base, needle_area_scale=1.0), geom=small)
    g_big = LightGrid.from_config(LightConfig(**base, needle_area_scale=1.0), EnvelopeConfig())
    g_big.rebuild_from_tree(tree, LightConfig(**base, needle_area_scale=1.0), geom=big)

    # cell_volume == 1.0 → grid sum == total deposited needle area, and it now tracks
    # leaf_size (bigger needles occlude more) instead of a fixed scalar.
    assert g_small.lai.sum() == pytest.approx(_leaf_area_at(tree, small))
    assert g_big.lai.sum() == pytest.approx(_leaf_area_at(tree, big))
    assert g_big.lai.sum() > g_small.lai.sum()

    # needle_area_scale multiplies linearly; 0 opts out of needle occlusion.
    g3 = LightGrid.from_config(LightConfig(**base, needle_area_scale=3.0), EnvelopeConfig())
    g3.rebuild_from_tree(tree, LightConfig(**base, needle_area_scale=3.0), geom=small)
    g0 = LightGrid.from_config(LightConfig(**base, needle_area_scale=0.0), EnvelopeConfig())
    g0.rebuild_from_tree(tree, LightConfig(**base, needle_area_scale=0.0), geom=small)
    assert g3.lai.sum() == pytest.approx(3.0 * g_small.lai.sum())
    assert g0.lai.sum() == pytest.approx(0.0)


def test_needle_fascicle_multiplicity_thickens_lai():
    """#7: a fascicle deposits fascicle_count needles' area into its cell, so the LAI
    grid reflects fascicle multiplicity — a 5-needle bundle self-shades ~5× a lone
    needle (slightly sub-linear: the intra-bundle splay shears each member's
    projected area). This is the geometry↔light↔diagnostic single-source invariant."""
    base = {"grid_origin": (0.0, 0.0, 0.0), "grid_size": (10.0, 10.0, 10.0),
            "grid_resolution": (10, 10, 10), "internode_area_scale": 0.0,
            "needle_area_scale": 1.0}
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))

    g1 = LightGrid.from_config(LightConfig(**base), EnvelopeConfig())
    g1.rebuild_from_tree(tree, LightConfig(**base), geom=GeomConfig(leaf_shape="linear", fascicle_count=1))
    g5 = LightGrid.from_config(LightConfig(**base), EnvelopeConfig())
    g5.rebuild_from_tree(tree, LightConfig(**base), geom=GeomConfig(leaf_shape="linear", fascicle_count=5))

    ratio = g5.lai.sum() / g1.lai.sum()
    assert 4.0 < ratio < 5.0


def test_leaf_area_scale_multiplies_deposit():
    """light.leaf_area_scale is a linear multiplier on the deposited real area;
    scale=0 opts out of leaf occlusion (byte-identical to no foliage)."""
    base = {"grid_origin": (0.0, 0.0, 0.0), "grid_size": (10.0, 10.0, 10.0),
            "grid_resolution": (10, 10, 10), "internode_area_scale": 0.0}
    tree = _make_tree_with_terminal_at(np.array([5.5, 7.5, 1.5]))

    grid1 = LightGrid.from_config(LightConfig(**base, leaf_area_scale=1.0), EnvelopeConfig())
    grid1.rebuild_from_tree(tree, LightConfig(**base, leaf_area_scale=1.0), geom=_GEOM)

    grid3 = LightGrid.from_config(LightConfig(**base, leaf_area_scale=3.0), EnvelopeConfig())
    grid3.rebuild_from_tree(tree, LightConfig(**base, leaf_area_scale=3.0), geom=_GEOM)

    grid0 = LightGrid.from_config(LightConfig(**base, leaf_area_scale=0.0), EnvelopeConfig())
    grid0.rebuild_from_tree(tree, LightConfig(**base, leaf_area_scale=0.0), geom=_GEOM)

    assert grid3.lai.sum() == pytest.approx(3.0 * grid1.lai.sum())
    assert grid0.lai.sum() == pytest.approx(0.0)


def test_rebuild_inject_internode_vertical():
    """A 1.0-length vertical internode of diameter 0.02 (radius 0.01) on cell_size 0.1
       → ~10 cells get LAI from lateral surface 2π·0.01·0.1 each."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(1.0, 1.0, 1.0),
        grid_resolution=(10, 10, 10),
        leaf_area_scale=0.0,             # disable leaf injection for this test
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

    grid.rebuild_from_tree(tree, cfg, geom=_GEOM)

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
        leaf_area_scale=0.0,
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

    grid.rebuild_from_tree(tree, cfg, geom=_GEOM)

    expected_total = 0.5 * (2 * np.pi * 0.01 * 1.0) / (0.1 * 0.1 * 0.1)
    assert grid.lai.sum() == pytest.approx(expected_total, rel=1e-4)


def test_rebuild_recomputes_radii():
    """rebuild_from_tree calls compute_radii to populate iod.diameter."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(1.0, 1.0, 1.0),
        grid_resolution=(10, 10, 10),
        leaf_area_scale=0.0,
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

    grid.rebuild_from_tree(tree, cfg, geom=_GEOM, r_tip=0.005, exponent=2.0)

    # After compute_radii: tip is at r_tip=0.005, single-internode tree → iod.diameter = 0.01
    assert iod.diameter == pytest.approx(0.01)


def test_rebuild_threads_vigor_diameter_gain():
    """rebuild_from_tree forwards vigor_ref/vigor_diameter_gain so the light grid's
    radii match the rendered geometry (vigor-seeded thickening, #37)."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(1.0, 1.0, 1.0),
        grid_resolution=(10, 10, 10),
        leaf_area_scale=0.0,
        internode_area_scale=1.0,
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    root = Node(position=np.array([0.5, 0.0, 0.5]))
    tip = Node(position=np.array([0.5, 1.0, 0.5]))
    iod = Internode(parent_node=root, child_node=tip, length=1.0, is_main_axis=True)
    iod.vigor = 1.0  # vigorous tip → seeds a thicker pipe when gain > 0
    root.children_internodes.append(iod)
    bud = Bud(position=tip.position.copy(), direction=np.array([0.0, 1.0, 0.0]), axis_order=0, parent_node=tip)
    tip.terminal_bud = bud
    tree = Tree(root=root, active_buds=[bud], all_internodes=[iod])

    grid.rebuild_from_tree(
        tree, cfg, geom=_GEOM, r_tip=0.005, exponent=2.0, vigor_ref=1.0, vigor_diameter_gain=0.25,
    )

    # sat = 1 - exp(-vigor/vigor_ref) = 1 - exp(-1); r = r_tip*(1 + 0.25*sat).
    sat = 1.0 - np.exp(-1.0)
    expected_diameter = 2.0 * 0.005 * (1.0 + 0.25 * sat)
    assert iod.diameter == pytest.approx(expected_diameter)
    # Strictly thicker than the pure-pipe diameter (0.01).
    assert iod.diameter > 0.01


def test_sample_transmission_empty_grid_returns_one():
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    # No LAI injected at all
    T = grid.sample_transmission(np.array([5.0, 5.0, 5.0]), np.array([0.0, 1.0, 0.0]), k=0.5)
    assert pytest.approx(1.0) == T


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
    assert pytest.approx(expected, rel=1e-2) == T


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
    assert pytest.approx(1.0) == T


def test_sample_transmission_zero_direction():
    """Zero-length direction is a no-op; return 1.0."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    T = grid.sample_transmission(np.array([5.0, 5.0, 5.0]), np.array([0.0, 0.0, 0.0]), k=0.5)
    assert pytest.approx(1.0) == T


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


def test_sample_transmission_half_step_offset():
    """A bud sitting inside a dense voxel should not have its OWN voxel's LAI count
       against it — the ray represents incoming light from outside."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(1.0, 1.0, 1.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    # Only ONE voxel is filled with LAI, and the bud sits inside it.
    grid.lai[5, 5, 5] = 10.0
    # Ray from the center of voxel (5,5,5), going +y.
    # The ray should pass through ONLY the cells ABOVE (5,5,5), not (5,5,5) itself.
    # All other cells have LAI=0, so T ≈ 1.0.
    T = grid.sample_transmission(np.array([0.55, 0.55, 0.55]), np.array([0.0, 1.0, 0.0]), k=0.5)
    assert pytest.approx(1.0, rel=1e-3) == T


def test_sample_transmission_outside_origin_marches_into_grid():
    """Ray starting outside the grid must still pick up LAI when it enters."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(10.0, 10.0, 10.0),
        grid_resolution=(10, 10, 10),
    )
    grid = LightGrid.from_config(cfg, EnvelopeConfig())
    L = 2.0
    grid.lai.fill(L)
    # Ray from outside (x=-5), going +x toward the dense grid. Travels ~10 units inside.
    k = 0.5
    T = grid.sample_transmission(np.array([-5.0, 5.0, 5.0]), np.array([1.0, 0.0, 0.0]), k=k)
    expected = np.exp(-k * L * 10.0)
    assert pytest.approx(expected, rel=0.1) == T   # generous tolerance — exact entry depends on discretization


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


def test_rebuild_from_forest_two_trees_lai_sums():
    """LAI from a forest of 2 trees = sum of per-tree LAI (when injected at the
    same cells; we make this trivial by giving each tree a single leaf at a
    distinct cell)."""
    from palubicki.config import (
        EnvelopeConfig,
        LightConfig,
    )
    from palubicki.sim.light import LightGrid
    from palubicki.sim.tree import Bud, Leaf, Node, Tree

    # Build a forest manually: 2 trees, each with a single terminal-bud leaf
    # at a known position.
    env = EnvelopeConfig(rx=1, ry=1, rz=1)
    light_cfg = LightConfig(
        enabled=True, grid_origin=(0, 0, 0), grid_size=(2, 2, 2),
        grid_resolution=(2, 2, 2), internode_area_scale=0.0,
    )
    grid = LightGrid.from_config(light_cfg, env)

    # Two trees, each at a separate position, both contributing one leaf
    root_a = Node(position=np.array([0.5, 0.5, 0.5]))
    bud_a = Bud(position=root_a.position.copy(), direction=np.array([0, 1, 0]),
                axis_order=0, parent_node=root_a)
    root_a.terminal_bud = bud_a
    root_a.leaves.append(Leaf(parent_node=root_a, azimuth=0.0, birth_time=0.0))
    tree_a = Tree(root=root_a, active_buds=[bud_a])

    root_b = Node(position=np.array([1.5, 0.5, 0.5]))
    bud_b = Bud(position=root_b.position.copy(), direction=np.array([0, 1, 0]),
                axis_order=0, parent_node=root_b)
    root_b.terminal_bud = bud_b
    root_b.leaves.append(Leaf(parent_node=root_b, azimuth=0.0, birth_time=0.0))
    tree_b = Tree(root=root_b, active_buds=[bud_b])

    from palubicki.sim.forest import Forest
    forest = Forest(
        trees=[tree_a, tree_b],
        seeds=[],
        obstacles=[],
        per_tree_cfgs=[],
        markers=None,   # type: ignore[arg-type]
    )

    grid.rebuild_from_forest(forest, light_cfg, geom=_GEOM, r_tip=0.005, exponent=2.49)

    cell_volume = float(np.prod(grid.cell_size))
    # Each single-leaf tree deposits the same real blade area into its own cell.
    expected_lai = _leaf_area_at(tree_a) / cell_volume
    assert expected_lai > 0.0
    # Cell (0,0,0) holds tree_a's leaf; cell (1,0,0) holds tree_b's leaf
    assert grid.lai[0, 0, 0] == np.float32(expected_lai)
    assert grid.lai[1, 0, 0] == np.float32(expected_lai)


def test_rebuild_from_forest_applies_obstacle_mask():
    from palubicki.config import (
        EnvelopeConfig,
        LightConfig,
        ObstacleAABB,
    )
    from palubicki.sim.light import LightGrid
    from palubicki.sim.obstacles import LAI_OPAQUE

    env = EnvelopeConfig()
    light_cfg = LightConfig(
        enabled=True, grid_origin=(0, 0, 0), grid_size=(4, 4, 4),
        grid_resolution=(4, 4, 4),
    )
    grid = LightGrid.from_config(light_cfg, env)

    # Build a minimal forest with an obstacle and a precomputed mask
    from palubicki.sim.obstacles import AABBObstacle
    obstacle = AABBObstacle(ObstacleAABB(min=(0.0, 0.0, 0.0), max=(2.0, 2.0, 2.0)))
    mask = obstacle.voxelize(grid)
    assert mask.sum() > 0

    from palubicki.sim.forest import Forest
    forest = Forest(
        trees=[],
        seeds=[],
        obstacles=[obstacle],
        per_tree_cfgs=[],
        markers=None,   # type: ignore[arg-type]
        obstacle_voxel_mask=mask,
    )

    grid.rebuild_from_forest(forest, light_cfg, geom=_GEOM, r_tip=0.005, exponent=2.49)

    # Cells in mask should be LAI_OPAQUE; others zero
    assert (grid.lai[mask] == np.float32(LAI_OPAQUE)).all()
    assert (grid.lai[~mask] == np.float32(0.0)).all()
