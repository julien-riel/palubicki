from palubicki.config import load_config
from palubicki.geom.leaves import build_leaves_primitive, selected_leaves
from palubicki.geom.mesh import Material
from palubicki.sim.simulator import simulate
from palubicki.sim.tree import LeafState


def _mat():
    return Material(name="leaf", base_color=(0.4, 0.6, 0.2, 1.0), metallic=0.0,
                    roughness=0.85, base_color_texture_png=None, alpha_mode="MASK",
                    alpha_cutoff=0.5, double_sided=True)


def _oak_tree(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={"seed": 0},
                      output=tmp_path / "t.glb", species="oak")
    return simulate(cfg), cfg


def test_selected_leaves_only_active(tmp_path):
    tree, cfg = _oak_tree(tmp_path)
    g = cfg.geom
    recs = selected_leaves(tree, foliage_depth=g.foliage_depth,
                           needle_cluster_spacing=g.needle_cluster_spacing)
    assert len(recs) > 0
    assert all(leaf.state is LeafState.ACTIVE for leaf, _d, _s, _p in recs)
    first_leaf = recs[0][0]
    first_leaf.state = LeafState.SENESCENT
    recs2 = selected_leaves(tree, foliage_depth=g.foliage_depth,
                            needle_cluster_spacing=g.needle_cluster_spacing)
    assert len(recs2) < len(recs)


def test_build_leaves_primitive_nonempty(tmp_path):
    tree, cfg = _oak_tree(tmp_path)
    g = cfg.geom
    prim = build_leaves_primitive(
        tree, leaf_size=g.leaf_size, material=_mat(), aspect=g.leaf_aspect,
        splay_deg=g.leaf_splay_deg, foliage_depth=g.foliage_depth,
        needle_cluster_spacing=g.needle_cluster_spacing, sun_shade_k=g.leaf_sun_shade_k,
        leaf_shape=g.leaf_shape, leaf_margin=g.leaf_margin,
        leaf_margin_depth=g.leaf_margin_depth, leaf_margin_count=g.leaf_margin_count,
    )
    assert prim.positions.shape[0] > 0
    assert prim.indices.shape[0] % 3 == 0


def test_build_leaves_primitive_empty_when_no_active(tmp_path):
    tree, cfg = _oak_tree(tmp_path)
    g = cfg.geom
    for leaf in tree.all_leaves():
        leaf.state = LeafState.ABSCISSED
    prim = build_leaves_primitive(
        tree, leaf_size=g.leaf_size, material=_mat(), aspect=g.leaf_aspect,
        splay_deg=g.leaf_splay_deg, foliage_depth=g.foliage_depth,
        needle_cluster_spacing=g.needle_cluster_spacing, sun_shade_k=g.leaf_sun_shade_k,
        leaf_shape=g.leaf_shape, leaf_margin=g.leaf_margin,
        leaf_margin_depth=g.leaf_margin_depth, leaf_margin_count=g.leaf_margin_count,
    )
    assert prim.positions.shape[0] == 0
