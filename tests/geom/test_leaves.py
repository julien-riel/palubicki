import numpy as np

from palubicki.geom.leaves import build_leaves_primitive
from palubicki.geom.mesh import Material
from palubicki.sim.tree import Bud, BudState, Internode, Node, Tree


def _mat():
    return Material(name="leaf", base_color=(1, 1, 1, 1), metallic=0.0, roughness=1.0,
                    base_color_texture_png=b"\x89PNG\r\n\x1a\n",
                    alpha_mode="MASK", alpha_cutoff=0.5, double_sided=True)


def _tree_with_n_terminal_buds(n):
    root = Node(position=np.zeros(3))
    tree = Tree(root=root)
    for i in range(n):
        node = Node(position=np.array([float(i), 1.0, 0.0]))
        bud = Bud(position=node.position.copy(), direction=np.array([0.0, 1.0, 0.0]),
                  axis_order=0, parent_node=node, state=BudState.ACTIVE)
        node.terminal_bud = bud
        tree.active_buds.append(bud)
    return tree


def test_one_bud_default_shape_vert_count():
    """Default leaf_shape=ovate (base N=16) + entire margin + cluster=1:
    per face = 16 boundary + 1 anchor = 17 verts and 48 indices.
    Ovate is parametric → n_planes=1 (single plane, no cross-blade sliver)
    → 17 verts, 48 indices."""
    tree = _tree_with_n_terminal_buds(1)
    prim = build_leaves_primitive(tree, leaf_size=0.1, material=_mat())
    assert prim.positions.shape == (17, 3)
    assert prim.indices.shape == (48,)


def test_dead_buds_excluded():
    tree = _tree_with_n_terminal_buds(1)
    tree.active_buds[0].state = BudState.DEAD
    prim = build_leaves_primitive(tree, leaf_size=0.1, material=_mat())
    assert prim.positions.shape == (0, 3)


def test_three_buds_yields_3x_default_blade_verts():
    """3 buds × 17 verts (ovate, n_planes=1) = 51 verts; 3 × 48 = 144 indices."""
    tree = _tree_with_n_terminal_buds(3)
    prim = build_leaves_primitive(tree, leaf_size=0.1, material=_mat())
    assert prim.positions.shape == (51, 3)
    assert prim.indices.shape == (144,)


def test_indices_within_bounds():
    tree = _tree_with_n_terminal_buds(2)
    prim = build_leaves_primitive(tree, leaf_size=0.1, material=_mat())
    assert prim.indices.max() < prim.positions.shape[0]


def _tree_one_apex_with_internode(light_factor: float):
    """Build a 2-node tree with one internode of the requested light_factor
    and one terminal bud on the child node."""
    root = Node(position=np.zeros(3))
    child = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(
        parent_node=root, child_node=child, length=1.0,
        is_main_axis=True, light_factor=light_factor,
    )
    root.children_internodes.append(iod)
    child.parent_internode = iod
    bud = Bud(
        position=child.position.copy(),
        direction=np.array([0.0, 1.0, 0.0]),
        axis_order=0, parent_node=child, state=BudState.ACTIVE,
    )
    child.terminal_bud = bud
    tree = Tree(root=root)
    tree.active_buds.append(bud)
    tree.all_internodes.append(iod)
    return tree


def _leaf_extent(prim):
    """Return the (x, y, z) bounding box diagonal of the leaf primitive."""
    pos = prim.positions
    return float(np.linalg.norm(pos.max(axis=0) - pos.min(axis=0)))


def test_leaf_size_unchanged_when_k_zero():
    """k=0 → leaf extent is identical regardless of light_factor."""
    t_sun = _tree_one_apex_with_internode(light_factor=1.0)
    t_shade = _tree_one_apex_with_internode(light_factor=0.2)
    p_sun = build_leaves_primitive(t_sun, leaf_size=0.1, material=_mat(),
                                   sun_shade_k=0.0)
    p_shade = build_leaves_primitive(t_shade, leaf_size=0.1, material=_mat(),
                                     sun_shade_k=0.0)
    assert abs(_leaf_extent(p_sun) - _leaf_extent(p_shade)) < 1e-6


def test_leaf_size_scales_with_shadow():
    """k=1, light_factor=0.5 → leaf size ~1.5x the full-sun leaf."""
    t_sun = _tree_one_apex_with_internode(light_factor=1.0)
    t_shade = _tree_one_apex_with_internode(light_factor=0.5)
    p_sun = build_leaves_primitive(t_sun, leaf_size=0.1, material=_mat(),
                                   sun_shade_k=1.0)
    p_shade = build_leaves_primitive(t_shade, leaf_size=0.1, material=_mat(),
                                     sun_shade_k=1.0)
    e_sun = _leaf_extent(p_sun)
    e_shade = _leaf_extent(p_shade)
    assert e_shade > e_sun * 1.3, f"expected shade > 1.3x sun, got {e_shade}/{e_sun}"


def test_leaf_size_clamped_high():
    """k=5, light_factor=0 → eff_size clamped at 2*leaf_size, not exploded."""
    t_shade = _tree_one_apex_with_internode(light_factor=0.0)
    t_sun = _tree_one_apex_with_internode(light_factor=1.0)
    p_shade = build_leaves_primitive(t_shade, leaf_size=0.1, material=_mat(),
                                     sun_shade_k=5.0)
    p_sun = build_leaves_primitive(t_sun, leaf_size=0.1, material=_mat(),
                                   sun_shade_k=5.0)
    ratio = _leaf_extent(p_shade) / _leaf_extent(p_sun)
    # Clamp says shade ≤ 2 * leaf_size, sun = leaf_size → ratio ≤ 2.0 + tolerance.
    assert ratio <= 2.0 + 1e-6


def test_leaf_size_clamped_low():
    """If somehow eff_size would dip below 0.5*leaf_size, it is clamped up.
    With k=5, light_factor=1.0 the formula yields exactly leaf_size, so we
    construct a synthetic regression: light_factor > 1 (shouldn't happen in
    practice but the clamp must still hold)."""
    t = _tree_one_apex_with_internode(light_factor=2.0)
    p = build_leaves_primitive(t, leaf_size=0.1, material=_mat(), sun_shade_k=5.0)
    # eff_size raw = 0.1 * (1 + 5 * (1 - 2)) = 0.1 * -4 = -0.4 → clamped to 0.05
    # Resulting extent must be at least the half-size quad diagonal.
    assert _leaf_extent(p) > 0.0  # i.e. not collapsed to zero
    # And not bigger than the half-clamp would allow (with petiole offset, etc.)
    # The reference (k=0, lf=1) quad has extent E0; the clamped-low quad must
    # have extent ≥ 0.5*E0.
    t_ref = _tree_one_apex_with_internode(light_factor=1.0)
    p_ref = build_leaves_primitive(t_ref, leaf_size=0.1, material=_mat(), sun_shade_k=0.0)
    assert _leaf_extent(p) >= 0.5 * _leaf_extent(p_ref) - 1e-6


def test_linear_shape_keeps_cross_blade():
    """leaf_shape=linear should still emit cross-blade (n_planes=2) so needles
    don't disappear when viewed edge-on. Linear blade has 4 boundary verts +
    1 anchor = 5 verts/face and 12 indices/face; cross-blade → 10 verts and
    24 indices per cluster member.
    1 bud × cluster_count=1 × 2 planes = 10 verts, 24 indices.
    """
    tree = _tree_with_n_terminal_buds(1)
    prim = build_leaves_primitive(
        tree, leaf_size=0.06, material=_mat(),
        leaf_shape="linear",
    )
    assert prim.positions.shape == (10, 3)
    assert prim.indices.shape == (24,)


def test_leaves_follow_sag_offset_at_apex():
    """When the apex node has a downward sag_offset, leaves should be emitted
    at the bent position, not the raw position."""
    import numpy as np
    from palubicki.geom.leaves import build_leaves_primitive
    from palubicki.geom.mesh import Material
    from palubicki.sim.tree import Bud, BudState, Internode, Node, Tree

    root = Node(position=np.zeros(3))
    tip = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=root, child_node=tip, length=1.0,
                    is_main_axis=True, diameter=0.05)
    root.children_internodes.append(iod)
    tip.parent_internode = iod
    tree = Tree(root=root, all_internodes=[iod])
    bud = Bud(position=tip.position.copy(), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=tip)
    tip.terminal_bud = bud
    tree.active_buds = [bud]

    mat = Material(name="leaf", base_color=(0.4, 0.6, 0.2, 1.0),
                   metallic=0.0, roughness=1.0, base_color_texture_png=None,
                   alpha_mode="OPAQUE", alpha_cutoff=0.5, double_sided=True)

    prim_baseline = build_leaves_primitive(tree, leaf_size=0.1, material=mat,
                                           foliage_depth=1)
    baseline_y_mean = float(prim_baseline.positions[:, 1].mean())

    tip.sag_offset = np.array([0.0, -0.5, 0.0])
    prim_bent = build_leaves_primitive(tree, leaf_size=0.1, material=mat,
                                       foliage_depth=1)
    bent_y_mean = float(prim_bent.positions[:, 1].mean())

    assert bent_y_mean < baseline_y_mean - 0.4
