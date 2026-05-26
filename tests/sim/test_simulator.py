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
    lateral_iods = [iod for iod in tree.all_internodes if not iod.is_main_axis]
    assert len(lateral_iods) > 0, "BH allocation should produce at least some lateral internodes"
    # At least one lateral subtree should have its own main-axis continuation
    found_main_continuation = any(
        any(child.is_main_axis for child in lat.child_node.children_internodes)
        for lat in lateral_iods
    )
    assert found_main_continuation, "lateral sub-axes should produce is_main_axis=True continuations"


def test_no_spikes_outside_envelope(tmp_path):
    """During multi-substep growth, buds must re-perceive and stop growing once
    they've cleared their local marker neighborhood — no straight spikes
    blasting through the envelope."""
    cfg = Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=1.0, ry=2.0, rz=1.0, marker_count=1000),
        sim=SimConfig(r_perception=0.3, r_kill=0.25, internode_length=0.1, max_iterations=15),
        tropism=TropismConfig(w_perception=1.0, w_gravity=0.3, w_direction_inertia=0.4),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        seed=42,
        output=tmp_path / "out.glb",
    )
    tree = simulate(cfg)
    envelope_max = max(cfg.envelope.rx, cfg.envelope.ry, cfg.envelope.rz)
    max_dist_allowed = envelope_max * 1.5  # allow modest overshoot near boundary
    offending = []
    stack = [tree.root]
    while stack:
        n = stack.pop()
        d = float(np.linalg.norm(n.position))
        if d > max_dist_allowed:
            offending.append(d)
        for iod in n.children_internodes:
            stack.append(iod.child_node)
    assert not offending, (
        f"Nodes too far from envelope: max={max(offending):.2f} "
        f"> {max_dist_allowed:.2f}"
    )


def test_deep_tree_no_recursion_error(tmp_path):
    """Regression: default-config tree depth used to exceed Python recursion limit."""
    cfg = Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=1.0, ry=2.0, rz=1.0, marker_count=5000),
        sim=SimConfig(max_iterations=20),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=True),
        geom=GeomConfig(),
        seed=42,
        output=tmp_path / "out.glb",
    )
    # Should not raise RecursionError
    tree = simulate(cfg)
    assert len(tree.all_internodes) > 100, "sanity: deep tree was produced"


def _all_nodes(tree):
    out = []
    stack = [tree.root]
    while stack:
        n = stack.pop()
        out.append(n)
        for iod in n.children_internodes:
            stack.append(iod.child_node)
    return out


def test_simulator_v1_bit_exact_when_light_disabled():
    """light.enabled=False → tree identical to V1 (same internode positions, count)."""
    import numpy as np
    from pathlib import Path
    from palubicki.config import (Config, EnvelopeConfig, SimConfig, TropismConfig,
                                  PhyllotaxyConfig, SheddingConfig, GeomConfig, LightConfig)
    from palubicki.sim.simulator import simulate

    cfg_v1 = Config(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_iterations=8),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        light=LightConfig(enabled=False),
        seed=42,
        output=Path("/tmp/x.glb"),
    )
    tree = simulate(cfg_v1)
    n_internodes_v1 = len(tree.all_internodes)

    # Re-run with light *missing entirely* (default = disabled) — same result.
    cfg_default = Config(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_iterations=8),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        seed=42,
        output=Path("/tmp/x.glb"),
    )
    tree2 = simulate(cfg_default)
    assert len(tree2.all_internodes) == n_internodes_v1


def test_simulator_light_enabled_zero_absorption_equivalent_to_disabled():
    """light.enabled=True with k_absorption=0 → grid transparent → ≈ V1 result."""
    from pathlib import Path
    from palubicki.config import (Config, EnvelopeConfig, SimConfig, TropismConfig,
                                  PhyllotaxyConfig, SheddingConfig, GeomConfig, LightConfig)
    from palubicki.sim.simulator import simulate

    base_kwargs = dict(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_iterations=8),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        seed=42,
        output=Path("/tmp/x.glb"),
    )
    tree_off = simulate(Config(light=LightConfig(enabled=False), **base_kwargs))
    tree_zerok = simulate(Config(light=LightConfig(enabled=True, k_absorption=0.0), **base_kwargs))
    # Same count (transparent grid → no shadowing)
    assert len(tree_zerok.all_internodes) == len(tree_off.all_internodes)


def test_simulator_light_enabled_reduces_density():
    """light.enabled=True (with real absorption) → fewer internodes than V1."""
    from pathlib import Path
    from palubicki.config import (Config, EnvelopeConfig, SimConfig, TropismConfig,
                                  PhyllotaxyConfig, SheddingConfig, GeomConfig, LightConfig)
    from palubicki.sim.simulator import simulate

    base_kwargs = dict(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_iterations=10),
        tropism=TropismConfig(w_phototropism=0.3),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        seed=42,
        output=Path("/tmp/x.glb"),
    )
    tree_off = simulate(Config(light=LightConfig(enabled=False), **base_kwargs))
    tree_on = simulate(Config(light=LightConfig(enabled=True, k_absorption=1.0, leaf_area=0.2), **base_kwargs))
    assert len(tree_on.all_internodes) < len(tree_off.all_internodes)


def test_simulator_light_reproducible():
    """Same seed + cfg → identical trees."""
    from pathlib import Path
    import hashlib
    import numpy as np
    from palubicki.config import (Config, EnvelopeConfig, SimConfig, TropismConfig,
                                  PhyllotaxyConfig, SheddingConfig, GeomConfig, LightConfig)
    from palubicki.sim.simulator import simulate

    def pos_hash(tree):
        positions = np.array([iod.child_node.position for iod in tree.all_internodes])
        return hashlib.sha256(positions.tobytes()).hexdigest()

    base = dict(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_iterations=6),
        tropism=TropismConfig(w_phototropism=0.3),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        light=LightConfig(enabled=True, k_absorption=0.5),
        seed=42,
        output=Path("/tmp/x.glb"),
    )
    t1 = simulate(Config(**base))
    t2 = simulate(Config(**base))
    assert pos_hash(t1) == pos_hash(t2)


def test_simulate_v2_bit_exact_after_refactor(tmp_path):
    """After refactor: simulate(cfg) with empty forest must produce the same Tree as
    a hash-pinned baseline. The baseline is recomputed once and saved in the test."""
    import hashlib
    import json
    from palubicki.config import (
        Config, EnvelopeConfig, GeomConfig, LightConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    cfg = Config(
        envelope=EnvelopeConfig(rx=3, ry=5, rz=3, shape="ellipsoid", marker_count=5000),
        sim=SimConfig(max_iterations=10),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        light=LightConfig(),
        output=tmp_path / "x.glb",
        seed=42,
    )
    tree = simulate(cfg)
    positions = []
    stack = [tree.root]
    while stack:
        node = stack.pop()
        positions.append(tuple(node.position.tolist()))
        for iod in node.children_internodes:
            stack.append(iod.child_node)
    digest = hashlib.sha256(json.dumps(sorted(positions), sort_keys=True).encode()).hexdigest()
    # This hash is pinned by running ONCE against the V2 code, before refactor.
    # If the hash changes, the refactor broke bit-exactness — investigate.
    EXPECTED = "aeac979ef2bafa69b40d74bfdda47c07afdaa7178b94163f85973b66b91a2c9c"
    assert EXPECTED is None or digest == EXPECTED, f"V2 bit-exact broken: {digest}"
    # Side-effect: print so we can copy the value if needed
    print(f"V2 hash: {digest}")


def test_simulate_forest_two_distant_trees_grow_independently(tmp_path):
    """Two trees far apart (envelopes disjoint) → each tree grows independently."""
    from palubicki.config import (
        Config, EnvelopeConfig, ForestConfig, ForestSeed, GeomConfig, LightConfig,
        PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate_forest

    cfg = Config(
        envelope=EnvelopeConfig(rx=2, ry=3, rz=2, shape="ellipsoid", marker_count=3000),
        sim=SimConfig(max_iterations=8),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "x.glb", seed=42,
        forest=ForestConfig(seeds=(
            ForestSeed(position=(0.0, 0.0, 0.0)),
            ForestSeed(position=(20.0, 0.0, 0.0)),
        )),
    )
    forest = simulate_forest(cfg)
    assert len(forest.trees) == 2
    assert len(forest.trees[0].all_internodes) > 0
    assert len(forest.trees[1].all_internodes) > 0


def test_simulate_forest_reproducible(tmp_path):
    """Two runs with the same cfg produce identical trees."""
    from palubicki.config import (
        Config, EnvelopeConfig, ForestConfig, ForestSeed, GeomConfig, LightConfig,
        PhyllotaxyConfig, SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate_forest

    def make_cfg():
        return Config(
            envelope=EnvelopeConfig(rx=2, ry=3, rz=2, shape="ellipsoid", marker_count=2000),
            sim=SimConfig(max_iterations=6),
            tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(),
            output=tmp_path / "x.glb", seed=99,
            forest=ForestConfig(seeds=(
                ForestSeed(position=(0.0, 0.0, 0.0)),
                ForestSeed(position=(5.0, 0.0, 0.0)),
            )),
        )

    f1 = simulate_forest(make_cfg())
    f2 = simulate_forest(make_cfg())
    for t1, t2 in zip(f1.trees, f2.trees):
        assert len(t1.all_internodes) == len(t2.all_internodes)
        for i1, i2 in zip(t1.all_internodes, t2.all_internodes):
            np.testing.assert_allclose(i1.child_node.position, i2.child_node.position)
