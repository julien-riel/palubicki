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
        sim=SimConfig(r_perception=0.4, r_kill=0.12, shoot_extension_max=0.1, vigor_dormancy=0.5, max_simulation_years=4.0),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        seed=1, output=Path("/tmp/unused.glb"),
    )
    return simulate(cfg)


def test_default_cluster_default_shape_vert_count():
    """Per-bud per-face = 17 verts (ovate N=16 + anchor); default ovate →
    n_planes=1 (single plane, no cross-blade); cluster_count=1; so per-bud =
    17 verts, 48 indices."""
    tree = _small_tree()
    prim = build_leaves_primitive(tree, leaf_size=0.06,
                                  cluster_count=1, aspect=1.0, splay_deg=0.0,
                                  material=_stub_material())
    n_terminal = sum(1 for b in tree.active_buds if not b.parent_node.children_internodes)
    assert prim.positions.shape == (n_terminal * 17, 3)
    assert prim.indices.shape == (n_terminal * 48,)


def test_cluster_count_5_emits_5x_vertices_per_bud():
    """cluster_count=5, default ovate → n_planes=1; per-bud = 5×17 verts,
    5×48 indices."""
    tree = _small_tree()
    prim = build_leaves_primitive(tree, leaf_size=0.06,
                                  cluster_count=5, aspect=0.2, splay_deg=20.0,
                                  material=_stub_material())
    n_terminal = sum(1 for b in tree.active_buds if not b.parent_node.children_internodes)
    assert prim.positions.shape == (n_terminal * 5 * 17, 3)
    assert prim.indices.shape == (n_terminal * 5 * 48,)


def test_aspect_ratio_narrows_blade_along_axis_u():
    """With aspect=0.2, the blade width along its LOCAL u-axis is 0.2× the
    aspect=1.0 width. Measured in the leaf's own frame — recovered from the
    geometry — so the assertion is invariant to how the bud happens to be
    oriented in world space (it isn't aligned to any world axis in general).
    With ovate/entire defaults and n_planes=1, each bud has 17 verts."""
    tree = _small_tree()
    p1 = build_leaves_primitive(tree, leaf_size=0.06, cluster_count=1, aspect=1.0,
                                splay_deg=0.0, material=_stub_material())
    p2 = build_leaves_primitive(tree, leaf_size=0.06, cluster_count=1, aspect=0.2,
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
