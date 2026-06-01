import numpy as np

from palubicki.geom.leaves import build_leaves_primitive, leaf_basis
from palubicki.geom.mesh import Material
from palubicki.sim.tree import Bud, BudState, Internode, Leaf, LeafState, Node, Tree


def _mat():
    return Material(name="leaf", base_color=(1, 1, 1, 1), metallic=0.0, roughness=1.0,
                    base_color_texture_png=b"\x89PNG\r\n\x1a\n",
                    alpha_mode="MASK", alpha_cutoff=0.5, double_sided=True)


def _attach_leaves(node, count=1):
    """Attach `count` ACTIVE leaves to a node with distinct azimuths.

    Models the leaves-on-nodes (#14) emission: the old render-time cluster_count
    fan is now `count` separate Leaf objects. Vertex count is azimuth-independent.
    """
    for i in range(count):
        node.leaves.append(
            Leaf(parent_node=node, azimuth=float(i), birth_time=0.0,
                 state=LeafState.ACTIVE)
        )


def _tree_with_n_terminal_buds(n, leaves_per_node=1):
    root = Node(position=np.zeros(3))
    tree = Tree(root=root)
    for i in range(n):
        node = Node(position=np.array([float(i), 1.0, 0.0]))
        bud = Bud(position=node.position.copy(), direction=np.array([0.0, 1.0, 0.0]),
                  axis_order=0, parent_node=node, state=BudState.ACTIVE)
        node.terminal_bud = bud
        _attach_leaves(node, leaves_per_node)
        tree.active_buds.append(bud)
    return tree


def _linear_chain(n_internodes, length=1.0):
    """root -> n1 -> ... -> n{n_internodes}(apex). Each internode is_main_axis,
    length `length`. One terminal bud on the apex node."""
    root = Node(position=np.zeros(3))
    tree = Tree(root=root)
    prev = root
    for i in range(1, n_internodes + 1):
        node = Node(position=np.array([0.0, float(i) * length, 0.0]))
        iod = Internode(parent_node=prev, child_node=node, length=length,
                        is_main_axis=True, light_factor=1.0)
        prev.children_internodes.append(iod)
        node.parent_internode = iod
        tree.all_internodes.append(iod)
        # One leaf per non-root node so every leaf-bearing node (apex + walked-back
        # nodes within foliage_depth) carries exactly one Leaf.
        _attach_leaves(node, 1)
        prev = node
    bud = Bud(position=prev.position.copy(), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=prev, state=BudState.ACTIVE)
    prev.terminal_bud = bud
    tree.active_buds.append(bud)
    return tree


def test_spacing_zero_matches_default():
    """needle_cluster_spacing=0.0 is byte-identical to omitting the param."""
    tree = _linear_chain(3)
    p_default = build_leaves_primitive(tree, leaf_size=0.1, material=_mat(), foliage_depth=3)
    p_zero = build_leaves_primitive(tree, leaf_size=0.1, material=_mat(),
                                    foliage_depth=3, needle_cluster_spacing=0.0)
    assert np.array_equal(p_default.positions, p_zero.positions)
    assert np.array_equal(p_default.indices, p_zero.indices)


def test_spacing_zero_one_cluster_per_leaf_node():
    """depth=3 on a 3-internode chain -> 3 leaf-bearing nodes -> 3 ovate clusters
    -> 3 * 17 = 51 verts."""
    tree = _linear_chain(3)
    p = build_leaves_primitive(tree, leaf_size=0.1, material=_mat(),
                               foliage_depth=3, needle_cluster_spacing=0.0)
    assert p.positions.shape == (51, 3)


def test_along_shoot_multiplies_clusters():
    """spacing=0.5 on length-1.0 internodes: floor(1.0/0.5)+1 = 3 clusters each,
    3 leaf-bearing internodes -> 9 clusters -> 9 * 17 = 153 verts."""
    tree = _linear_chain(3)
    p = build_leaves_primitive(tree, leaf_size=0.1, material=_mat(),
                               foliage_depth=3, needle_cluster_spacing=0.5)
    assert p.positions.shape == (153, 3)


def test_along_shoot_caps_per_internode():
    """One long internode (length 10) at fine spacing is capped at 8 clusters."""
    tree = _linear_chain(1, length=10.0)
    p = build_leaves_primitive(tree, leaf_size=0.1, material=_mat(),
                               foliage_depth=1, needle_cluster_spacing=0.1)
    assert p.positions.shape == (8 * 17, 3)


def test_one_bud_default_shape_vert_count():
    """Default leaf_shape=ovate (base N=16) + entire margin + cluster=1:
    per face = 16 boundary + 1 anchor = 17 verts and 48 indices.
    Ovate is parametric → n_planes=1 (single plane, no cross-blade sliver)
    → 17 verts, 48 indices."""
    tree = _tree_with_n_terminal_buds(1)
    prim = build_leaves_primitive(tree, leaf_size=0.1, material=_mat())
    assert prim.positions.shape == (17, 3)
    assert prim.indices.shape == (48,)


def test_non_active_leaves_excluded():
    """Migrated from test_dead_buds_excluded: the renderer now draws node.leaves,
    so a non-ACTIVE leaf must produce no geometry (the leaves-on-nodes analogue of
    a dead bud bearing no foliage)."""
    tree = _tree_with_n_terminal_buds(1)
    apex_node = tree.active_buds[0].parent_node
    for leaf in apex_node.leaves:
        leaf.state = LeafState.ABSCISSED
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
    _attach_leaves(child, 1)
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
    from palubicki.sim.tree import Bud, Internode, Leaf, LeafState, Node, Tree

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
    tip.leaves.append(
        Leaf(parent_node=tip, azimuth=0.0, birth_time=0.0, state=LeafState.ACTIVE)
    )
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


def test_simple_kind_matches_default_output():
    """leaf_kind='simple' (the new default path) is byte-identical to the
    pre-compound single-blade output, for both n_planes=1 (ovate) and
    n_planes=2 (linear cross-blade)."""
    tree = _tree_with_n_terminal_buds(3)
    # n_planes=1 (ovate, default shape)
    p_old = build_leaves_primitive(tree, leaf_size=0.1, material=_mat(),
                                   foliage_depth=1)
    p_new = build_leaves_primitive(tree, leaf_size=0.1, material=_mat(),
                                   foliage_depth=1,
                                   leaf_kind="simple", leaflet_specs=None)
    np.testing.assert_array_equal(p_old.positions, p_new.positions)
    np.testing.assert_array_equal(p_old.normals, p_new.normals)
    np.testing.assert_array_equal(p_old.uvs, p_new.uvs)
    np.testing.assert_array_equal(p_old.indices, p_new.indices)

    # n_planes=2 (linear → cross-blade): the second-plane basis order must be
    # preserved, so the regression check covers it too.
    pl_old = build_leaves_primitive(tree, leaf_size=0.06, material=_mat(),
                                    foliage_depth=1, leaf_shape="linear")
    pl_new = build_leaves_primitive(tree, leaf_size=0.06, material=_mat(),
                                    foliage_depth=1, leaf_shape="linear",
                                    leaf_kind="simple", leaflet_specs=None)
    np.testing.assert_array_equal(pl_old.positions, pl_new.positions)
    np.testing.assert_array_equal(pl_old.normals, pl_new.normals)
    np.testing.assert_array_equal(pl_old.uvs, pl_new.uvs)
    np.testing.assert_array_equal(pl_old.indices, pl_new.indices)


def test_pinnate_vert_count_is_linear_in_leaflets():
    """A pinnate leaf emits one blade per leaflet, so vertex/index counts scale
    by len(layout.leaflets) over the simple (single-leaflet) baseline."""
    from palubicki.geom.compound_leaf import compound_layout
    from palubicki.geom.leaf_blade import build_blade
    from palubicki.geom.leaves import selected_leaves

    tree = _tree_with_n_terminal_buds(3)
    n_records = len(selected_leaves(tree, foliage_depth=1))

    specs = {
        "leaflet_count": 6, "leaflet_pair_count": 0, "terminal_leaflet": True,
        "rachis_length": 1.5, "petiole_length": 0.4, "rachis_radius": 0.045,
    }
    lay = compound_layout("pinnate", **specs)
    leaflets_per_leaf = len(lay.leaflets)  # 6 lateral + 1 terminal = 7

    prim = build_leaves_primitive(
        tree, leaf_size=0.06, material=_mat(), foliage_depth=1,
        leaf_kind="pinnate", leaflet_specs=specs,
    )
    # Ovate blade (default shape) has a fixed vertex count V.
    blade_pos = build_blade(length=1.0, width=1.0, shape="ovate", margin="entire")[0]
    v = blade_pos.shape[0]
    blade_idx = build_blade(length=1.0, width=1.0, shape="ovate", margin="entire")[3]
    m = blade_idx.shape[0]
    assert prim.positions.shape[0] == n_records * leaflets_per_leaf * v
    assert prim.indices.shape[0] == n_records * leaflets_per_leaf * m


def test_leaf_basis_no_droop_matches_inline_math():
    import math
    d = np.array([0.0, 1.0, 0.0])
    az, splay = 0.7, math.radians(30.0)
    u, up, w = leaf_basis(d, az, splay, 0.0)
    # orthonormal lateral/normal axes, unit leaf_up
    assert abs(np.linalg.norm(u) - 1.0) < 1e-9
    assert abs(np.linalg.norm(w) - 1.0) < 1e-9
    assert abs(np.linalg.norm(up) - 1.0) < 1e-9
    # splay tilts leaf_up off the stem by exactly splay (dot with d == cos splay)
    assert abs(float(np.dot(up, d)) - math.cos(splay)) < 1e-9


def test_leaf_basis_droop_rotates_toward_minus_y():
    import math
    # horizontal stem along +X, no splay -> leaf_up == +X
    d = np.array([1.0, 0.0, 0.0])
    _, up0, _ = leaf_basis(d, 0.0, 0.0, 0.0)
    assert abs(up0[0] - 1.0) < 1e-9
    # droop 90 deg -> leaf_up rotates to -Y
    _, up90, _ = leaf_basis(d, 0.0, 0.0, math.radians(90.0))
    assert up90[1] < -0.999


def test_leaf_basis_droop_is_rigid_preserves_splay_angle():
    import math
    d = np.array([0.0, 1.0, 0.0])
    az, splay, droop = 1.2, math.radians(35.0), math.radians(40.0)
    u0, up0, _ = leaf_basis(d, az, splay, 0.0)
    u1, up1, _ = leaf_basis(d, az, splay, droop)
    # the angle between lateral axis and leaf_up (the area-defining shear) is
    # invariant under the rigid droop rotation
    assert abs(float(np.dot(u0, up0)) - float(np.dot(u1, up1))) < 1e-9
