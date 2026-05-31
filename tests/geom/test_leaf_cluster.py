from pathlib import Path

import numpy as np
import pytest

from palubicki.config import (
    Config,
    EnvelopeConfig,
    GeomConfig,
    PhyllotaxyConfig,
    SheddingConfig,
    SimConfig,
    TropismConfig,
)
from palubicki.geom.leaves import build_leaves_primitive, selected_leaves
from palubicki.geom.mesh import Material
from palubicki.sim.simulator import simulate
from palubicki.sim.tree import Leaf, LeafState


def _stub_material() -> Material:
    return Material(
        name="leaf", base_color=(0.4, 0.6, 0.2, 1.0),
        metallic=0.0, roughness=0.85, base_color_texture_png=None,
        alpha_mode="MASK", alpha_cutoff=0.5, double_sided=True,
    )


def _small_tree():
    cfg = Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.5, ry=1.0, rz=0.5, marker_count=150),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, shoot_extension_max=0.1, vigor_dormancy=0.5, max_simulation_years=4.0),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        seed=1, output=Path("/tmp/unused.glb"),
    )
    return simulate(cfg)


def _topup_leaves(tree, per_node):
    """Top every leaf-bearing (selected) node up to `per_node` ACTIVE leaves.

    The old render-time cluster_count fan is now N separate Leaf objects on the
    node (#14). simulate() seats one leaf per node, so we add (per_node - 1) more
    with distinct azimuths to reproduce the old cluster_count=N geometry. Vertex
    count is azimuth-independent.
    """
    seen: set[int] = set()
    for leaf, _stem_dir, _iod, _pos in selected_leaves(tree, foliage_depth=1):
        node = leaf.parent_node
        if id(node) in seen:
            continue
        seen.add(id(node))
        existing = sum(1 for lf in node.leaves if lf.state is LeafState.ACTIVE)
        for i in range(existing, per_node):
            node.leaves.append(
                Leaf(parent_node=node, azimuth=float(i), birth_time=0.0,
                     state=LeafState.ACTIVE)
            )


def _n_selected_leaves(tree):
    return len(selected_leaves(tree, foliage_depth=1))


def test_default_cluster_default_shape_vert_count():
    """Per-leaf per-face = 17 verts (ovate N=16 + anchor); default ovate →
    n_planes=1 (single plane, no cross-blade); one leaf per node; so per-leaf =
    17 verts, 48 indices."""
    tree = _small_tree()
    prim = build_leaves_primitive(tree, leaf_size=0.06,
                                  aspect=1.0, splay_deg=0.0,
                                  material=_stub_material())
    n_leaves = _n_selected_leaves(tree)
    assert prim.positions.shape == (n_leaves * 17, 3)
    assert prim.indices.shape == (n_leaves * 48,)


def test_five_leaves_per_node_emits_5x_vertices():
    """Migrated from cluster_count=5: the render fan is now 5 Leaf objects per
    node. default ovate → n_planes=1; per-leaf = 17 verts, 48 indices, so 5
    leaves/node give 5× the one-leaf-per-node geometry."""
    tree = _small_tree()
    n_nodes = sum(
        1 for b in tree.active_buds if not b.parent_node.children_internodes
    )
    _topup_leaves(tree, per_node=5)
    prim = build_leaves_primitive(tree, leaf_size=0.06,
                                  aspect=0.2, splay_deg=20.0,
                                  material=_stub_material())
    assert prim.positions.shape == (n_nodes * 5 * 17, 3)
    assert prim.indices.shape == (n_nodes * 5 * 48,)


def test_aspect_ratio_narrows_blade_along_axis_u():
    """With aspect=0.2, the blade width along its LOCAL u-axis is 0.2× the
    aspect=1.0 width. Measured in the leaf's own frame — recovered from the
    geometry — so the assertion is invariant to how the bud happens to be
    oriented in world space (it isn't aligned to any world axis in general).
    With ovate/entire defaults and n_planes=1, each bud has 17 verts."""
    tree = _small_tree()
    p1 = build_leaves_primitive(tree, leaf_size=0.06, aspect=1.0,
                                splay_deg=0.0, material=_stub_material())
    p2 = build_leaves_primitive(tree, leaf_size=0.06, aspect=0.2,
                                splay_deg=0.0, material=_stub_material())
    # Isolate the first bud's verts (17 verts per bud with ovate/entire defaults).
    leaf1 = p1.positions[:17].astype(np.float64)
    leaf2 = p2.positions[:17].astype(np.float64)
    # aspect scales ONLY the local u-component, so the per-vertex displacement
    # leaf2 - leaf1 lies entirely along the (world-rotated) u-axis. Recover that
    # axis as the dominant singular vector of the displacement, then compare the
    # blade's extent projected onto it. No dependence on world-axis alignment.
    delta = leaf2 - leaf1
    u_hat = np.linalg.svd(delta, full_matrices=False)[2][0]
    w1 = float(np.ptp(leaf1 @ u_hat))
    w2 = float(np.ptp(leaf2 @ u_hat))
    assert w2 == pytest.approx(0.2 * w1, rel=0.1)
