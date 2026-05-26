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


def test_default_cluster_matches_old_cross_quad_vertex_count():
    tree = _small_tree()
    prim = build_leaves_primitive(tree, leaf_size=0.06,
                                  cluster_count=1, aspect=1.0, splay_deg=0.0,
                                  material=_stub_material())
    n_terminal = sum(1 for b in tree.active_buds if not b.parent_node.children_internodes)
    assert prim.positions.shape == (n_terminal * 8, 3)
    assert prim.indices.shape == (n_terminal * 12,)


def test_cluster_count_5_emits_5x_vertices_per_bud():
    tree = _small_tree()
    prim = build_leaves_primitive(tree, leaf_size=0.06,
                                  cluster_count=5, aspect=0.2, splay_deg=20.0,
                                  material=_stub_material())
    n_terminal = sum(1 for b in tree.active_buds if not b.parent_node.children_internodes)
    assert prim.positions.shape == (n_terminal * 5 * 8, 3)
    assert prim.indices.shape == (n_terminal * 5 * 12,)


def test_aspect_ratio_narrows_quads_along_axis_u():
    """With aspect=0.2, the first quad's u-axis half-extent is 0.2× the aspect=1.0 value."""
    tree = _small_tree()
    p1 = build_leaves_primitive(tree, leaf_size=0.06, cluster_count=1, aspect=1.0,
                                splay_deg=0.0, material=_stub_material())
    p2 = build_leaves_primitive(tree, leaf_size=0.06, cluster_count=1, aspect=0.2,
                                splay_deg=0.0, material=_stub_material())
    diag1 = np.linalg.norm(p1.positions[1] - p1.positions[0])  # width along axis_u for the first bud
    diag2 = np.linalg.norm(p2.positions[1] - p2.positions[0])
    assert diag2 == pytest.approx(0.2 * diag1, rel=1e-5)
