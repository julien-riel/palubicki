from __future__ import annotations

import math

import numpy as np
import pytest

from palubicki.sim.diagnostics import compute_metrics
from palubicki.sim.tree import Bud, BudState, Internode, Node, Tree


def _link(parent: Node, child: Node, *, is_main_axis: bool = True) -> Internode:
    """Create + bidirectionally link an internode between parent and child."""
    iod = Internode(
        parent_node=parent, child_node=child,
        length=float(np.linalg.norm(child.position - parent.position)),
        is_main_axis=is_main_axis,
    )
    parent.children_internodes.append(iod)
    child.parent_internode = iod
    return iod


def _make_tree_y_shape() -> Tree:
    """Trunk + two equal leaf branches:

           c1     c2
            \\   /
             m
             |
             root
    """
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    c1 = Node(position=np.array([0.5, 1.5, 0.0]))
    c2 = Node(position=np.array([-0.5, 1.5, 0.0]))
    tree = Tree(root=root)
    trunk = _link(root, mid, is_main_axis=True)
    # Two laterals at the fork — neither marked main axis (terminal fork).
    b1 = _link(mid, c1, is_main_axis=False)
    b2 = _link(mid, c2, is_main_axis=False)
    tree.all_internodes.extend([trunk, b1, b2])
    return tree


def test_strahler_y_shape():
    tree = _make_tree_y_shape()
    m = compute_metrics(tree)
    assert m["strahler_order_max"] == 2
    assert m["strahler_order_histogram"] == {1: 2, 2: 1}
    # Bifurcation ratio: count(1) / count(2) = 2 / 1 = 2.0
    assert m["horton_bifurcation_ratio"] == {1: 2.0}
    assert m["horton_bifurcation_ratio_mean"] == pytest.approx(2.0)


def _make_pectinate_3level() -> Tree:
    """A pectinate-style tree:

              g
             /
            f---leaf3
           /
          e---leaf2
         /
        d---leaf1
        |
        root

    Three forks; each non-leaf has children of orders (1, k) where
    k grows from 1 → 2 → 3 → ... Strahler order at root = 2
    (the unique-max rule keeps each internal node at max+0 since
    the higher-order child is unique at every fork).
    """
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    d = Node(position=np.array([0.0, 1.0, 0.0]))
    leaf1 = Node(position=np.array([0.5, 1.0, 0.0]))
    e = Node(position=np.array([0.0, 2.0, 0.0]))
    leaf2 = Node(position=np.array([0.5, 2.0, 0.0]))
    f = Node(position=np.array([0.0, 3.0, 0.0]))
    leaf3 = Node(position=np.array([0.5, 3.0, 0.0]))
    g = Node(position=np.array([0.0, 4.0, 0.0]))

    tree = Tree(root=root)
    trunk = _link(root, d, is_main_axis=True)
    l1 = _link(d, leaf1, is_main_axis=False)
    main1 = _link(d, e, is_main_axis=True)
    l2 = _link(e, leaf2, is_main_axis=False)
    main2 = _link(e, f, is_main_axis=True)
    l3 = _link(f, leaf3, is_main_axis=False)
    main3 = _link(f, g, is_main_axis=True)
    tree.all_internodes.extend([trunk, l1, main1, l2, main2, l3, main3])
    return tree


def test_strahler_pectinate_unique_max_rule():
    tree = _make_pectinate_3level()
    m = compute_metrics(tree)
    # main3, l3, l2, l1 are all leaves (order 1). main2 has children
    # (main3, l3): both order 1 → tie → main2 is order 2. main1's children
    # (main2, l2): main2=2, l2=1 → unique max → main1 is order 2. trunk's
    # children (main1, l1): main1=2, l1=1 → unique max → trunk is order 2.
    assert m["strahler_order_max"] == 2
    assert m["strahler_order_histogram"] == {1: 4, 2: 3}
    # ratio 1→2 = 4/3
    assert m["horton_bifurcation_ratio"][1] == pytest.approx(4.0 / 3.0)


def test_strahler_single_internode():
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    child = Node(position=np.array([0.0, 1.0, 0.0]))
    tree = Tree(root=root)
    iod = _link(root, child, is_main_axis=True)
    tree.all_internodes.append(iod)
    m = compute_metrics(tree)
    assert m["strahler_order_max"] == 1
    assert m["strahler_order_histogram"] == {1: 1}
    assert m["horton_bifurcation_ratio"] == {}
    assert math.isnan(m["horton_bifurcation_ratio_mean"])


def test_strahler_empty_tree():
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    tree = Tree(root=root)
    m = compute_metrics(tree)
    assert m["strahler_order_max"] == 0
    assert m["strahler_order_histogram"] == {}
    assert m["horton_bifurcation_ratio"] == {}
    assert math.isnan(m["horton_bifurcation_ratio_mean"])


def _make_trunk_with_lateral(branch_dir: np.ndarray,
                              branch_is_main_axis: bool = False) -> Tree:
    """Trunk along +Y; one lateral at the trunk's child node, pointing in
    `branch_dir` (any non-zero vector — gets normalized to position the
    lateral end node 1 unit from mid)."""
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    branch_dir = np.asarray(branch_dir, dtype=np.float64)
    branch_dir = branch_dir / np.linalg.norm(branch_dir)
    lat_end = mid.position + branch_dir
    lat_node = Node(position=lat_end)
    tree = Tree(root=root)
    trunk = _link(root, mid, is_main_axis=True)
    lat = _link(mid, lat_node, is_main_axis=branch_is_main_axis)
    tree.all_internodes.extend([trunk, lat])
    return tree


def test_insertion_angle_vs_parent_45():
    tree = _make_trunk_with_lateral(
        branch_dir=np.array([math.sin(math.radians(45.0)),
                              math.cos(math.radians(45.0)), 0.0]),
    )
    m = compute_metrics(tree)
    assert 1 in m["insertion_angle_deg_vs_parent"]
    stats = m["insertion_angle_deg_vs_parent"][1]
    assert stats["mean"] == pytest.approx(45.0, abs=1e-6)
    assert stats["stddev"] == pytest.approx(0.0, abs=1e-9)
    assert stats["n"] == 1


def test_insertion_angle_vs_main_sibling_60():
    """Trunk +Y up to mid; mid has a main-axis continuation also at +Y, plus
    a lateral at 60° from that direction. Angle vs parent = 60°, and angle
    vs main_sibling = 60° (parent and main_sibling happen to be colinear)."""
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    top = Node(position=np.array([0.0, 2.0, 0.0]))
    angle = math.radians(60.0)
    lat_dir = np.array([math.sin(angle), math.cos(angle), 0.0])
    lat_node = Node(position=mid.position + lat_dir)

    tree = Tree(root=root)
    trunk = _link(root, mid, is_main_axis=True)
    cont = _link(mid, top, is_main_axis=True)
    lat = _link(mid, lat_node, is_main_axis=False)
    tree.all_internodes.extend([trunk, cont, lat])

    m = compute_metrics(tree)
    p_stats = m["insertion_angle_deg_vs_parent"][1]
    s_stats = m["insertion_angle_deg_vs_main_sibling"][1]
    assert p_stats["mean"] == pytest.approx(60.0, abs=1e-6)
    assert p_stats["n"] == 1
    assert s_stats["mean"] == pytest.approx(60.0, abs=1e-6)
    assert s_stats["n"] == 1


def test_insertion_angle_vs_main_sibling_differs_from_vs_parent():
    """Trunk +Y; main-sibling at 30° in +X half-plane; lateral at 30° in -X
    half-plane → 60° vs main-sibling, but 30° vs parent (trunk)."""
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    a30 = math.radians(30.0)
    main_dir = np.array([math.sin(a30), math.cos(a30), 0.0])
    lat_dir = np.array([-math.sin(a30), math.cos(a30), 0.0])
    top = Node(position=mid.position + main_dir)
    lat_node = Node(position=mid.position + lat_dir)

    tree = Tree(root=root)
    trunk = _link(root, mid, is_main_axis=True)
    cont = _link(mid, top, is_main_axis=True)
    lat = _link(mid, lat_node, is_main_axis=False)
    tree.all_internodes.extend([trunk, cont, lat])

    m = compute_metrics(tree)
    assert m["insertion_angle_deg_vs_parent"][1]["mean"] == pytest.approx(30.0, abs=1e-6)
    assert m["insertion_angle_deg_vs_main_sibling"][1]["mean"] == pytest.approx(60.0, abs=1e-6)


def test_divergence_angle_known_pair():
    """Trunk +Y, two main-axis continuations along +Y. At each continuation's
    child node, one lateral. Lateral 1 points along +X (azimuth 0°);
    lateral 2 points at azimuth 137.5° in the perpendicular basis used by
    phyllotaxy.py → divergence = 137.5°.
    """
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    n1 = Node(position=np.array([0.0, 1.0, 0.0]))
    n2 = Node(position=np.array([0.0, 2.0, 0.0]))
    az2_rad = math.radians(137.5)
    # phyllotaxy's _frame_perpendicular_to(+Y) yields right=+X, up=-Z.
    # Lateral 1 is purely +X (azimuth 0° in that basis); some +Y component
    # is fine — azimuth uses only the perpendicular-plane projection.
    lat1_dir = np.array([1.0, 0.5, 0.0])
    lat2_dir = np.array([math.cos(az2_rad), 0.5, -math.sin(az2_rad)])

    lat1_node = Node(position=n1.position + lat1_dir)
    lat2_node = Node(position=n2.position + lat2_dir)

    tree = Tree(root=root)
    trunk = _link(root, n1, is_main_axis=True)
    cont = _link(n1, n2, is_main_axis=True)
    l1 = _link(n1, lat1_node, is_main_axis=False)
    l2 = _link(n2, lat2_node, is_main_axis=False)
    tree.all_internodes.extend([trunk, cont, l1, l2])

    m = compute_metrics(tree)
    assert 1 in m["divergence_angle_deg"]
    stats = m["divergence_angle_deg"][1]
    assert stats["mean"] == pytest.approx(137.5, abs=0.5)
    assert stats["n"] == 1


def test_divergence_angle_single_lateral_contributes_nothing():
    tree = _make_trunk_with_lateral(branch_dir=np.array([1.0, 1.0, 0.0]))
    m = compute_metrics(tree)
    # One lateral on one axis → no divergence pairs at all.
    assert m["divergence_angle_deg"] == {}


def test_bud_state_histogram_walks_all_nodes():
    """A DORMANT bud on a non-active-list node must be counted."""
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    child = Node(position=np.array([0.0, 1.0, 0.0]))
    tree = Tree(root=root)
    iod = _link(root, child, is_main_axis=True)
    tree.all_internodes.append(iod)

    term = Bud(position=child.position, direction=np.array([0.0, 1.0, 0.0]),
               axis_order=0, parent_node=child)
    child.terminal_bud = term
    tree.active_buds.append(term)

    dormant = Bud(position=child.position, direction=np.array([1.0, 0.0, 0.0]),
                  axis_order=1, parent_node=child)
    dormant.state = BudState.DORMANT
    child.lateral_buds.append(dormant)

    reserve = Bud(position=root.position, direction=np.array([0.0, 0.0, 1.0]),
                  axis_order=0, parent_node=root)
    reserve.state = BudState.RESERVE
    root.dormant_reserve_buds.append(reserve)

    m = compute_metrics(tree)
    hist = m["bud_state_histogram"]
    assert hist["ACTIVE"] == 1
    assert hist["DORMANT"] == 1
    assert hist["RESERVE"] == 1
    assert hist.get("DEAD", 0) == 0


def test_sympodial_count_uses_node_flag():
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    a = Node(position=np.array([0.0, 1.0, 0.0]))
    b = Node(position=np.array([0.0, 2.0, 0.0]))
    a.sympodial_fork = True
    b.sympodial_fork = True
    tree = Tree(root=root)
    i1 = _link(root, a, is_main_axis=True)
    i2 = _link(a, b, is_main_axis=True)
    tree.all_internodes.extend([i1, i2])

    m = compute_metrics(tree)
    assert m["sympodial_fork_count"] == 2


def test_height_uses_sag_offset():
    """Node positioned at y=5 with sag_offset y=-0.4 → tree_height = 4.6."""
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    top = Node(position=np.array([0.0, 5.0, 0.0]))
    top.sag_offset = np.array([0.0, -0.4, 0.0])
    tree = Tree(root=root)
    iod = _link(root, top, is_main_axis=True)
    tree.all_internodes.append(iod)

    m = compute_metrics(tree)
    assert m["tree_height"] == pytest.approx(4.6, abs=1e-9)


def test_crown_radius_band_only():
    """Wide low node (below 0.4*height) is ignored; narrower high node defines
    the crown_radius."""
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    low_wide = Node(position=np.array([3.0, 0.5, 0.0]))
    mid = Node(position=np.array([0.0, 2.0, 0.0]))
    high_narrow = Node(position=np.array([1.5, 4.0, 0.0]))
    top = Node(position=np.array([0.0, 5.0, 0.0]))
    tree = Tree(root=root)
    tree.all_internodes.append(_link(root, low_wide, is_main_axis=False))
    tree.all_internodes.append(_link(root, mid, is_main_axis=True))
    tree.all_internodes.append(_link(mid, high_narrow, is_main_axis=False))
    tree.all_internodes.append(_link(mid, top, is_main_axis=True))

    m = compute_metrics(tree)
    # 0.4 * 5.0 = 2.0; only high_narrow (y=4) and top (y=5) are in band.
    # high_narrow r=1.5; top r=0. Crown = 1.5.
    assert m["tree_height"] == pytest.approx(5.0)
    assert m["crown_radius"] == pytest.approx(1.5, abs=1e-9)


def test_trunk_base_diameter():
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    top = Node(position=np.array([0.0, 1.0, 0.0]))
    tree = Tree(root=root)
    iod = _link(root, top, is_main_axis=True)
    iod.diameter = 0.18
    tree.all_internodes.append(iod)
    m = compute_metrics(tree)
    assert m["trunk_base_diameter"] == pytest.approx(0.18)


def test_root_only_tree_returns_zeros():
    """Degenerate single-node tree must not crash."""
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    tree = Tree(root=root)
    m = compute_metrics(tree)
    assert m["strahler_order_max"] == 0
    assert m["sympodial_fork_count"] == 0
    assert m["tree_height"] == pytest.approx(0.0)
    assert m["trunk_base_diameter"] == pytest.approx(0.0)
    assert m["crown_radius"] == pytest.approx(0.0)
    assert m["total_leaf_area"] == pytest.approx(0.0)


@pytest.mark.slow
def test_compute_effective_leaf_size_extraction_preserves_geom_output():
    """Refactor invariant: build_leaves_primitive's positions array must be
    bit-identical before and after we extract compute_effective_leaf_size.

    Hash captured pre-refactor; assertion fails if the refactor drifted.
    """
    from pathlib import Path
    from palubicki.config import load_config
    from palubicki.geom.leaves import build_leaves_primitive
    from palubicki.geom.mesh import Material
    from palubicki.sim.simulator import simulate

    cfg = load_config(yaml_path=None, cli_overrides={"seed": 0},
                      output=Path("tree.glb"), species="oak")
    tree = simulate(cfg)

    g = cfg.geom
    mat = Material(name="leaves_a", base_color=(0.2, 0.6, 0.2, 1.0),
                   metallic=0.0, roughness=1.0, base_color_texture_png=None,
                   alpha_mode="OPAQUE", alpha_cutoff=0.5, double_sided=True)
    prim = build_leaves_primitive(
        tree,
        leaf_size=g.leaf_size,
        material=mat,
        cluster_count=g.leaf_cluster_count,
        aspect=g.leaf_aspect,
        splay_deg=g.leaf_splay_deg,
        foliage_depth=g.foliage_depth,
        sun_shade_k=g.leaf_sun_shade_k,
    )
    h = float(np.sum(prim.positions.astype(np.float64) ** 2))
    # PRE-REFACTOR baseline captured from oak/seed-0 run before the
    # compute_effective_leaf_size extraction.
    EXPECTED_HASH = 4392811.55783453  # noqa: N806
    assert h == pytest.approx(EXPECTED_HASH, rel=0, abs=1e-9), (
        f"Pre-refactor hash: {h!r}. If this is the first run before the "
        f"refactor, replace EXPECTED_HASH with this value and re-run."
    )


@pytest.mark.slow
def test_leaf_area_matches_geom_helper():
    """Cross-check: compute total_leaf_area via the diagnostics harness and
    independently sum quad areas from the rendered positions array. Must
    match to within float epsilon.

    The independent computation walks the rendered triangles (each pair
    forms a quad) and sums (1/2)|edge1 × edge2| — this exercises the
    rendered geometry, not the helper, so it's a real cross-check of the
    helper's formula, not a self-check.
    """
    from pathlib import Path
    from palubicki.config import load_config
    from palubicki.geom.leaves import build_leaves_primitive
    from palubicki.geom.mesh import Material
    from palubicki.sim.simulator import simulate

    cfg = load_config(yaml_path=None, cli_overrides={"seed": 0},
                      output=Path("tree.glb"), species="oak")
    tree = simulate(cfg)

    g = cfg.geom
    mat = Material(
        name="leaves_a",
        base_color=(0.2, 0.6, 0.2, 1.0),
        metallic=0.0,
        roughness=1.0,
        base_color_texture_png=None,
        alpha_mode="OPAQUE",
        alpha_cutoff=0.5,
        double_sided=True,
    )
    prim = build_leaves_primitive(
        tree,
        leaf_size=g.leaf_size,
        material=mat,
        cluster_count=g.leaf_cluster_count,
        aspect=g.leaf_aspect,
        splay_deg=g.leaf_splay_deg,
        foliage_depth=g.foliage_depth,
        sun_shade_k=g.leaf_sun_shade_k,
    )

    pos = prim.positions.astype(np.float64)
    idx = prim.indices.reshape(-1, 3)
    e1 = pos[idx[:, 1]] - pos[idx[:, 0]]
    e2 = pos[idx[:, 2]] - pos[idx[:, 0]]
    tri_areas = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    rendered_area = float(tri_areas.sum())

    m = compute_metrics(tree, cfg=cfg)
    assert m["total_leaf_area"] == pytest.approx(rendered_area, rel=1e-5)


def test_compute_metrics_accepts_list_of_trees():
    """Two hand-built trees with known heights → mean/stddev/per_seed."""
    def trunk_to_height(h: float) -> Tree:
        root = Node(position=np.array([0.0, 0.0, 0.0]))
        top = Node(position=np.array([0.0, h, 0.0]))
        tree = Tree(root=root)
        iod = _link(root, top, is_main_axis=True)
        tree.all_internodes.append(iod)
        return tree

    t1 = trunk_to_height(2.0)
    t2 = trunk_to_height(4.0)
    m = compute_metrics([t1, t2])

    h = m["tree_height"]
    assert h["mean"] == pytest.approx(3.0)
    assert h["stddev"] == pytest.approx(1.0)
    assert h["per_seed"] == [pytest.approx(2.0), pytest.approx(4.0)]

    hist = m["strahler_order_histogram"]
    assert hist[1]["mean"] == pytest.approx(1.0)
    assert hist[1]["per_seed"] == [1, 1]


def test_compute_metrics_multi_seed_missing_axis_order():
    """Tree A has order-2 internodes; tree B doesn't. The order-2 stats
    appear in the aggregate with per_seed=[val, None] and mean/stddev
    computed over the non-None subset."""
    rootA = Node(position=np.array([0.0, 0.0, 0.0]))
    midA = Node(position=np.array([0.0, 1.0, 0.0]))
    latA = Node(position=np.array([1.0, 1.5, 0.0]))
    sublatA = Node(position=np.array([1.5, 2.0, 0.0]))
    treeA = Tree(root=rootA)
    treeA.all_internodes.extend([
        _link(rootA, midA, is_main_axis=True),
        _link(midA, latA, is_main_axis=False),
        _link(latA, sublatA, is_main_axis=False),
    ])

    rootB = Node(position=np.array([0.0, 0.0, 0.0]))
    midB = Node(position=np.array([0.0, 1.0, 0.0]))
    latB = Node(position=np.array([1.0, 1.5, 0.0]))
    treeB = Tree(root=rootB)
    treeB.all_internodes.extend([
        _link(rootB, midB, is_main_axis=True),
        _link(midB, latB, is_main_axis=False),
    ])

    m = compute_metrics([treeA, treeB])
    assert 1 in m["insertion_angle_deg_vs_parent"]
    assert 2 in m["insertion_angle_deg_vs_parent"]
    o2 = m["insertion_angle_deg_vs_parent"][2]
    assert "mean" in o2
    assert o2["per_seed"][1] is None


def test_format_report_single_seed_includes_keys_and_flag():
    from palubicki.sim.diagnostics import format_report

    metrics = {
        "strahler_order_max": 4,
        "strahler_order_histogram": {1: 78, 2: 18, 3: 5, 4: 1},
        "horton_bifurcation_ratio": {1: 4.33, 2: 3.60, 3: 5.00},
        "horton_bifurcation_ratio_mean": 4.27,
        "insertion_angle_deg_vs_parent": {
            1: {"mean": 52.1, "stddev": 6.4, "n": 18},
        },
        "insertion_angle_deg_vs_main_sibling": {},
        "divergence_angle_deg": {
            1: {"mean": 137.4, "stddev": 9.2, "n": 12},
        },
        "sympodial_fork_count": 3,
        "bud_state_histogram": {"ACTIVE": 24, "DORMANT": 7, "DEAD": 12, "RESERVE": 5},
        "tree_height": 5.42,
        "trunk_base_diameter": 0.18,
        "crown_radius": 2.91,
        "total_leaf_area": 12.4,
    }
    out = format_report(metrics, seeds=[0], species="oak")
    assert "tree_height" in out
    assert ("bif_ratio" in out) or ("bifurcation_ratio" in out)
    assert "✓" in out  # bif_ratio_mean=4.27 is in [3.0, 5.0]


def test_format_report_multi_seed_has_mean_stddev():
    from palubicki.sim.diagnostics import format_report

    multi = {
        "strahler_order_max": {"mean": 4.0, "stddev": 0.0, "per_seed": [4, 4]},
        "strahler_order_histogram": {1: {"mean": 78.0, "stddev": 0.0, "per_seed": [78, 78]}},
        "horton_bifurcation_ratio": {},
        "horton_bifurcation_ratio_mean": {"mean": 4.18, "stddev": 0.41, "per_seed": [4.0, 4.36]},
        "insertion_angle_deg_vs_parent": {1: {"mean": 51.7, "stddev": 1.2, "per_seed": [50.5, 52.9]}},
        "insertion_angle_deg_vs_main_sibling": {},
        "divergence_angle_deg": {1: {"mean": 136.9, "stddev": 2.3, "per_seed": [135.0, 138.8]}},
        "sympodial_fork_count": {"mean": 3.4, "stddev": 1.1, "per_seed": [2, 5]},
        "bud_state_histogram": {"DEAD": {"mean": 11.6, "stddev": 2.1, "per_seed": [10, 13]}},
        "tree_height": {"mean": 5.31, "stddev": 0.18, "per_seed": [5.13, 5.49]},
        "trunk_base_diameter": {"mean": 0.17, "stddev": 0.01, "per_seed": [0.16, 0.18]},
        "crown_radius": {"mean": 2.84, "stddev": 0.21, "per_seed": [2.6, 3.0]},
        "total_leaf_area": {"mean": 11.9, "stddev": 0.8, "per_seed": [11.1, 12.7]},
    }
    out = format_report(multi, seeds=[0, 1], species="oak")
    assert "mean" in out
    assert "stddev" in out
    assert "✓" in out  # bif_ratio_mean=4.18 still in range
