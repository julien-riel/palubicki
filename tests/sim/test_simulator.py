import numpy as np

from palubicki.config import (
    Config, EnvelopeConfig, GeomConfig, PhyllotaxyConfig,
    SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.sim.simulator import simulate


def _tiny_config(tmp_path):
    return Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=1.0, ry=2.0, rz=1.0, marker_count=500),
        sim=SimConfig(
            r_perception=0.3, theta_perception_deg=80.0, r_kill=0.1,
            internode_length=0.1, alpha_basipetal=2.0, lambda_apical=0.55,
            max_iterations=10,
        ),
        tropism=TropismConfig(w_perception=1.0, w_gravity=0.2, w_direction_inertia=0.3),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        seed=42,
        output=tmp_path / "out.glb",
    )


def test_simulate_produces_tree_with_internodes(tmp_path):
    cfg = _tiny_config(tmp_path)
    tree = simulate(cfg)
    assert tree.root is not None
    assert len(tree.all_internodes) > 0


def test_simulate_is_deterministic(tmp_path):
    cfg = _tiny_config(tmp_path)
    tree_a = simulate(cfg)
    tree_b = simulate(cfg)
    assert len(tree_a.all_internodes) == len(tree_b.all_internodes)
    pos_a = np.array([n.position for n in _all_nodes(tree_a)])
    pos_b = np.array([n.position for n in _all_nodes(tree_b)])
    np.testing.assert_array_equal(pos_a, pos_b)


def test_simulate_stops_at_max_iterations(tmp_path):
    cfg = _tiny_config(tmp_path)
    # 0 iterations -> just root, no internodes
    cfg_0 = Config(
        envelope=cfg.envelope,
        sim=SimConfig(max_iterations=0, internode_length=0.1),
        tropism=cfg.tropism, phyllotaxy=cfg.phyllotaxy,
        shedding=cfg.shedding, geom=cfg.geom,
        seed=cfg.seed, output=cfg.output,
    )
    tree = simulate(cfg_0)
    assert len(tree.all_internodes) == 0


def test_lateral_axes_get_main_internodes(tmp_path):
    """A lateral bud's terminal continuation should produce is_main_axis=True internodes."""
    cfg = _tiny_config(tmp_path)
    tree = simulate(cfg)
    # Walk and check: every lateral subtree should contain at least one is_main_axis=True
    # internode, OR be a single-internode lateral that just started.
    lateral_iods = [iod for iod in tree.all_internodes
                    if not iod.is_main_axis]
    # Among lateral starts (is_main_axis=False), check if their child node has any
    # is_main_axis=True descendant within 3 generations.
    found_main_continuation_on_lateral = False
    for lat in lateral_iods:
        stack = [(lat.child_node, 0)]
        while stack:
            node, depth = stack.pop()
            if depth > 3:
                continue
            for child_iod in node.children_internodes:
                if child_iod.is_main_axis:
                    found_main_continuation_on_lateral = True
                    break
                stack.append((child_iod.child_node, depth + 1))
            if found_main_continuation_on_lateral:
                break
        if found_main_continuation_on_lateral:
            break
    # If no lateral subtree has any descendants, this assertion is vacuous — skip if so.
    if any(iod.child_node.children_internodes for iod in lateral_iods):
        assert found_main_continuation_on_lateral, (
            "lateral sub-axes should produce is_main_axis=True continuations"
        )


def _all_nodes(tree):
    out = []
    stack = [tree.root]
    while stack:
        n = stack.pop()
        out.append(n)
        for iod in n.children_internodes:
            stack.append(iod.child_node)
    return out
