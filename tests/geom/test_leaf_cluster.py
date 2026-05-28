from pathlib import Path

import numpy as np
import pytest

from palubicki.config import (
    Config, EnvelopeConfig, GeomConfig, LightConfig, PhyllotaxyConfig,
    SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.geom.leaves import build_leaves_primitive
from palubicki.geom.mesh import Material
from palubicki.sim.simulator import simulate


def _stub_material() -> Material:
    return Material(
        name="leaf", base_color=(0.4, 0.6, 0.2, 1.0),
        metallic=0.0, roughness=0.85, base_color_texture_png=None,
        alpha_mode="MASK", alpha_cutoff=0.5, double_sided=True,
    )


def _small_tree():
    cfg = Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.5, ry=1.0, rz=0.5, marker_count=150),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1, max_iterations=4),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        seed=1, output=Path("/tmp/unused.glb"),
    )
    return simulate(cfg)


def test_default_cluster_default_shape_vert_count():
    """Per-bud per-face = 17 verts (ovate N=16 + anchor); two faces per cluster
    member; cluster_count=1; so per-bud = 34 verts, 96 indices."""
    tree = _small_tree()
    prim = build_leaves_primitive(tree, leaf_size=0.06,
                                  cluster_count=1, aspect=1.0, splay_deg=0.0,
                                  material=_stub_material())
    n_terminal = sum(1 for b in tree.active_buds if not b.parent_node.children_internodes)
    assert prim.positions.shape == (n_terminal * 34, 3)
    assert prim.indices.shape == (n_terminal * 96,)


def test_cluster_count_5_emits_5x_vertices_per_bud():
    tree = _small_tree()
    prim = build_leaves_primitive(tree, leaf_size=0.06,
                                  cluster_count=5, aspect=0.2, splay_deg=20.0,
                                  material=_stub_material())
    n_terminal = sum(1 for b in tree.active_buds if not b.parent_node.children_internodes)
    assert prim.positions.shape == (n_terminal * 5 * 34, 3)
    assert prim.indices.shape == (n_terminal * 5 * 96,)


def test_aspect_ratio_narrows_blade_along_axis_u():
    """With aspect=0.2, the width along axis_u is 0.2× the aspect=1.0 width.
    Measured via the u-axis extent of the first leaf's bounding box (34 verts
    per bud, cluster_count=1)."""
    tree = _small_tree()
    p1 = build_leaves_primitive(tree, leaf_size=0.06, cluster_count=1, aspect=1.0,
                                splay_deg=0.0, material=_stub_material())
    p2 = build_leaves_primitive(tree, leaf_size=0.06, cluster_count=1, aspect=0.2,
                                splay_deg=0.0, material=_stub_material())
    # Isolate the first bud's verts (34 verts per bud with ovate/entire defaults).
    leaf1 = p1.positions[:34]
    leaf2 = p2.positions[:34]
    bbox1 = leaf1.max(axis=0) - leaf1.min(axis=0)
    bbox2 = leaf2.max(axis=0) - leaf2.min(axis=0)
    # The narrower extent of bbox2 (along u-axis) should be ~0.2× that of bbox1.
    # Pick the smallest of the three axes as the u-extent.
    u_extent_1 = float(min(bbox1))
    u_extent_2 = float(min(bbox2))
    assert u_extent_2 == pytest.approx(0.2 * u_extent_1, rel=0.1)
