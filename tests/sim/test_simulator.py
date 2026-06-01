import numpy as np

from palubicki.config import (
    Config,
    EnvelopeConfig,
    GeomConfig,
    PhyllotaxyConfig,
    SheddingConfig,
    SimConfig,
    TropismConfig,
)
from palubicki.sim.simulator import simulate


def _tiny_config(tmp_path):
    return Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=1.0, ry=2.0, rz=1.0, marker_count=500),
        sim=SimConfig(
            r_perception=0.3, theta_perception_deg=80.0, r_kill=0.1,
            shoot_extension_max=0.1, vigor_dormancy=0.5, alpha_basipetal=2.0, lambda_apical=0.55,
            max_simulation_years=10.0,
        ),
        tropism=TropismConfig(w_perception=1.0, w_orthotropy_main=0.2, w_direction_inertia=0.3),
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


def test_simulate_stops_at_max_simulation_years(tmp_path):
    cfg = _tiny_config(tmp_path)
    # 0 iterations -> just root, no internodes
    cfg_0 = Config(
        envelope=cfg.envelope,
        sim=SimConfig(max_simulation_years=0.0, shoot_extension_max=0.1, vigor_dormancy=0.5),
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
        sim=SimConfig(r_perception=0.3, r_kill=0.25, shoot_extension_max=0.1, vigor_dormancy=0.5, max_simulation_years=15.0),
        tropism=TropismConfig(w_perception=1.0, w_orthotropy_main=0.3, w_direction_inertia=0.4),
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
        sim=SimConfig(max_simulation_years=20.0),
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
    from pathlib import Path

    from palubicki.config import (
        Config,
        EnvelopeConfig,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    cfg_v1 = Config(
        envelope=EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_simulation_years=8.0),
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
        sim=SimConfig(max_simulation_years=8.0),
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

    from palubicki.config import (
        Config,
        EnvelopeConfig,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    base_kwargs = {
        "envelope": EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        "sim": SimConfig(max_simulation_years=8.0),
        "tropism": TropismConfig(),
        "phyllotaxy": PhyllotaxyConfig(),
        "shedding": SheddingConfig(),
        "geom": GeomConfig(),
        "seed": 42,
        "output": Path("/tmp/x.glb"),
    }
    tree_off = simulate(Config(light=LightConfig(enabled=False), **base_kwargs))
    tree_zerok = simulate(Config(light=LightConfig(enabled=True, k_absorption=0.0), **base_kwargs))
    # Same count (transparent grid → no shadowing)
    assert len(tree_zerok.all_internodes) == len(tree_off.all_internodes)


def test_simulator_light_enabled_reduces_density():
    """light.enabled=True (with real absorption) → fewer internodes than V1."""
    from pathlib import Path

    from palubicki.config import (
        Config,
        EnvelopeConfig,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    base_kwargs = {
        "envelope": EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        "sim": SimConfig(max_simulation_years=10.0),
        "tropism": TropismConfig(w_phototropism=0.3),
        "phyllotaxy": PhyllotaxyConfig(),
        "shedding": SheddingConfig(),
        "geom": GeomConfig(),
        "seed": 42,
        "output": Path("/tmp/x.glb"),
    }
    tree_off = simulate(Config(light=LightConfig(enabled=False), **base_kwargs))
    tree_on = simulate(Config(light=LightConfig(enabled=True, k_absorption=1.0, leaf_area_scale=92.0), **base_kwargs))
    assert len(tree_on.all_internodes) < len(tree_off.all_internodes)


def test_simulator_light_reproducible():
    """Same seed + cfg → identical trees."""
    import hashlib
    from pathlib import Path

    import numpy as np

    from palubicki.config import (
        Config,
        EnvelopeConfig,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    def pos_hash(tree):
        positions = np.array([iod.child_node.position for iod in tree.all_internodes])
        return hashlib.sha256(positions.tobytes()).hexdigest()

    base = {
        "envelope": EnvelopeConfig(rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        "sim": SimConfig(max_simulation_years=6.0),
        "tropism": TropismConfig(w_phototropism=0.3),
        "phyllotaxy": PhyllotaxyConfig(),
        "shedding": SheddingConfig(),
        "geom": GeomConfig(),
        "light": LightConfig(enabled=True, k_absorption=0.5),
        "seed": 42,
        "output": Path("/tmp/x.glb"),
    }
    t1 = simulate(Config(**base))
    t2 = simulate(Config(**base))
    assert pos_hash(t1) == pos_hash(t2)


def test_simulate_forest_two_distant_trees_grow_independently(tmp_path):
    """Two trees far apart (envelopes disjoint) → each tree grows independently."""
    from palubicki.config import (
        Config,
        EnvelopeConfig,
        ForestConfig,
        ForestSeed,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate_forest

    cfg = Config(
        envelope=EnvelopeConfig(rx=2, ry=3, rz=2, shape="ellipsoid", marker_count=3000),
        sim=SimConfig(max_simulation_years=8.0),
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
        Config,
        EnvelopeConfig,
        ForestConfig,
        ForestSeed,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate_forest

    def make_cfg():
        return Config(
            envelope=EnvelopeConfig(rx=2, ry=3, rz=2, shape="ellipsoid", marker_count=2000),
            sim=SimConfig(max_simulation_years=6.0),
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
    for t1, t2 in zip(f1.trees, f2.trees, strict=True):
        assert len(t1.all_internodes) == len(t2.all_internodes)
        for i1, i2 in zip(t1.all_internodes, t2.all_internodes, strict=True):
            np.testing.assert_allclose(i1.child_node.position, i2.child_node.position)


def test_simulate_forest_segment_blocked_makes_bud_dormant(tmp_path):
    """A wall right above the root → the trunk bud becomes DORMANT after 1 step (cannot grow)."""
    from palubicki.config import (
        Config,
        EnvelopeConfig,
        ForestConfig,
        ForestSeed,
        GeomConfig,
        LightConfig,
        ObstacleAABB,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate_forest

    cfg = Config(
        envelope=EnvelopeConfig(rx=2, ry=3, rz=2, shape="ellipsoid", marker_count=2000),
        sim=SimConfig(max_simulation_years=4.0, shoot_extension_max=0.5, vigor_dormancy=0.5),
        tropism=TropismConfig(w_orthotropy_main=0.0),   # don't fight gravity, just go up
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),  # disable shedding for clarity
        geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "x.glb", seed=42,
        forest=ForestConfig(
            seeds=(ForestSeed(position=(0.0, 0.0, 0.0)),),
            # Wall covering y ∈ [0.1, 0.4], i.e. blocks any segment going up from y=0
            obstacles=(ObstacleAABB(min=(-5, 0.1, -5), max=(5, 0.4, 5)),),
        ),
    )
    forest = simulate_forest(cfg)
    # The trunk can't grow upward — the bud should be DORMANT and the tree should
    # have at most 0 internodes from upward growth (laterals may still grow if any).
    upward_internodes = sum(
        1 for iod in forest.trees[0].all_internodes
        if (iod.child_node.position[1] - iod.parent_node.position[1]) > 0.05
    )
    assert upward_internodes == 0


def test_simulate_forest_bud_inside_obstacle_dies(tmp_path):
    """A bud growing into an obstacle (point-inside test, not just segment) → DEAD."""
    from palubicki.config import (
        Config,
        EnvelopeConfig,
        ForestConfig,
        ForestSeed,
        GeomConfig,
        LightConfig,
        ObstacleSphere,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate_forest
    cfg = Config(
        envelope=EnvelopeConfig(rx=2, ry=3, rz=2, shape="ellipsoid", marker_count=2000),
        sim=SimConfig(max_simulation_years=6.0, shoot_extension_max=0.3, vigor_dormancy=0.5),
        tropism=TropismConfig(w_orthotropy_main=0.0),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(), light=LightConfig(),
        output=tmp_path / "x.glb", seed=42,
        forest=ForestConfig(
            seeds=(ForestSeed(position=(0.0, 0.0, 0.0)),),
            # Big sphere centered far above the tree — buds reaching it get killed
            obstacles=(ObstacleSphere(center=(0.0, 5.0, 0.0), radius=0.5),),
        ),
    )
    forest = simulate_forest(cfg)
    # No internode endpoint should lie inside the sphere
    sphere_center = np.array([0.0, 5.0, 0.0])
    for iod in forest.trees[0].all_internodes:
        dist = np.linalg.norm(iod.child_node.position - sphere_center)
        assert dist > 0.5, f"internode endpoint {iod.child_node.position} is inside the obstacle"


def test_internode_length_jitter_disabled_is_deterministic():
    """With jitter=0, repeated runs at the same seed yield identical per-internode
    lengths, and every length lies in (0, shoot_extension_max] (the saturation ceiling)."""
    from pathlib import Path

    from palubicki.config import (
        Config,
        EnvelopeConfig,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    def run():
        cfg = Config(
            envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=300),
            sim=SimConfig(r_perception=0.4, r_kill=0.12, shoot_extension_max=0.3,
                          vigor_ref=1.0, vigor_dormancy=0.5,
                          internode_length_jitter=0.0, max_simulation_years=6.0),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(enabled=False),
            geom=GeomConfig(),
            light=LightConfig(enabled=False),
            seed=7,
            output=Path("/tmp/_pj_dummy.glb"),
        )
        tree = simulate(cfg)
        return [iod.length for iod in tree.all_internodes]

    a = run()
    b = run()
    assert a == b, "jitter=0 + same seed should be bit-identical"
    assert len(a) > 0
    assert all(0.0 < L <= 0.3 for L in a), f"lengths must be in (0, 0.3], got {sorted(set(a))}"


def test_internode_length_jitter_deterministic_with_seed():
    """Same seed → same internode length sequence; different seed → different sequence."""
    from pathlib import Path

    from palubicki.config import (
        Config,
        EnvelopeConfig,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    def run(seed):
        cfg = Config(
            envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=300),
            sim=SimConfig(r_perception=0.4, r_kill=0.12, shoot_extension_max=0.3,
                          vigor_ref=1.0, vigor_dormancy=0.5,
                          internode_length_jitter=0.15, max_simulation_years=6.0),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(enabled=False),
            geom=GeomConfig(),
            light=LightConfig(enabled=False),
            seed=seed,
            output=Path("/tmp/_pj_dummy.glb"),
        )
        tree = simulate(cfg)
        return [iod.length for iod in tree.all_internodes]

    a = run(7)
    b = run(7)
    assert a == b

    c = run(8)
    assert a != c

    # Jitter factor is clamped to <= 1.5; applied to the saturating length which is
    # itself <= shoot_extension_max, so lengths live in (0, 0.3 * 1.5].
    assert len(a) > 5
    assert all(0.0 < L <= 0.3 * 1.5 for L in a), f"lengths out of range: {sorted(set(a))}"


def test_simulator_emits_dormant_reserves_when_configured(tmp_path):
    """When phyllotaxy.dormant_reserve_count > 0, every new node carries
    that many RESERVE buds in node.dormant_reserve_buds."""
    from palubicki.config import (
        Config,
        EnvelopeConfig,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate
    from palubicki.sim.tree import BudState

    cfg = Config(
        envelope=EnvelopeConfig(shape="half_ellipsoid", rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_simulation_years=8.0),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(mode="alternate", dormant_reserve_count=2),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        light=LightConfig(),
        output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)

    # Walk all nodes, count reserves.
    seen_nodes = 0
    total_reserves = 0
    stack = [tree.root]
    while stack:
        n = stack.pop()
        seen_nodes += 1
        for r in n.dormant_reserve_buds:
            assert r.state is BudState.RESERVE
        # Root has no parent emission, so it should have 0 reserves; others should have 2.
        if n is not tree.root:
            assert len(n.dormant_reserve_buds) == 2, (
                f"expected 2 reserves on emitted node, got {len(n.dormant_reserve_buds)}"
            )
        total_reserves += len(n.dormant_reserve_buds)
        for iod in n.children_internodes:
            stack.append(iod.child_node)

    assert seen_nodes > 1
    assert total_reserves > 0


def test_simulator_no_reserves_when_count_zero(tmp_path):
    from palubicki.config import (
        Config,
        EnvelopeConfig,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    cfg = Config(
        envelope=EnvelopeConfig(shape="half_ellipsoid", rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(max_simulation_years=5.0),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(mode="alternate", dormant_reserve_count=0),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        light=LightConfig(),
        output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)
    stack = [tree.root]
    while stack:
        n = stack.pop()
        assert n.dormant_reserve_buds == []
        for iod in n.children_internodes:
            stack.append(iod.child_node)


def test_simulator_kills_shaded_buds_when_enabled(tmp_path):
    """With shade_mortality enabled and light enabled, a bud forced under
    threshold for N consecutive steps must end up DEAD."""
    from palubicki.config import (
        Config,
        EnvelopeConfig,
        GeomConfig,
        LightConfig,
        PhyllotaxyConfig,
        ShadeMortalityConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate
    from palubicki.sim.tree import BudState

    cfg = Config(
        envelope=EnvelopeConfig(shape="half_ellipsoid", rx=2.0, ry=3.0, rz=2.0, marker_count=2000),
        sim=SimConfig(
            max_simulation_years=15.0,
            shade_mortality=ShadeMortalityConfig(
                enabled=True, light_threshold=0.99, n_consecutive_steps=2,
            ),
        ),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(mode="alternate"),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        light=LightConfig(enabled=True, k_absorption=2.0),
        output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)
    # With threshold near 1.0 and high absorption, most buds end up shaded → dead.
    dead = 0
    alive = 0
    stack = [tree.root]
    while stack:
        n = stack.pop()
        for b in ([n.terminal_bud] if n.terminal_bud else []) + n.lateral_buds:
            if b.state is BudState.DEAD:
                dead += 1
            elif b.state is BudState.ACTIVE:
                alive += 1
        for iod in n.children_internodes:
            stack.append(iod.child_node)
    assert dead > 0, "expected shade mortality to kill at least one bud"


def test_internodes_record_birth_time_and_length_target(tmp_path):
    from palubicki.config import (
        Config,
        ElongationConfig,
        EnvelopeConfig,
        GeomConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    cfg = Config(
        envelope=EnvelopeConfig(rx=2.0, ry=2.0, rz=2.0, marker_count=500),
        sim=SimConfig(max_simulation_years=5.0,
                      elongation=ElongationConfig(enabled=True, tau_years=2.0)),
        tropism=TropismConfig(w_orthotropy_main=0.3),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        output=tmp_path / "tree.glb",
        seed=42,
    )
    tree = simulate(cfg)
    assert len(tree.all_internodes) > 0
    for iod in tree.all_internodes:
        assert 0 <= iod.birth_time < cfg.sim.max_simulation_years
        assert iod.length_target > 0.0


def test_bud_and_internode_have_vigor_fields():
    import numpy as np

    from palubicki.sim.tree import Bud, Internode, Node
    root = Node(position=np.zeros(3))
    bud = Bud(position=np.zeros(3), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=root)
    assert bud.recent_vigor == 0.0
    child = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=root, child_node=child, length=1.0, is_main_axis=True)
    assert iod.vigor == 0.0


def test_finalization_snaps_length_to_target(tmp_path):
    """After simulate(), every internode must have length == length_target."""
    from palubicki.config import (
        Config,
        ElongationConfig,
        EnvelopeConfig,
        GeomConfig,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    cfg = Config(
        envelope=EnvelopeConfig(rx=2.0, ry=2.0, rz=2.0, marker_count=500),
        sim=SimConfig(max_simulation_years=8.0,
                      elongation=ElongationConfig(enabled=True, tau_years=3.0)),
        tropism=TropismConfig(w_orthotropy_main=0.3),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        output=tmp_path / "tree.glb",
        seed=42,
    )
    tree = simulate(cfg)
    assert len(tree.all_internodes) > 0
    for iod in tree.all_internodes:
        assert iod.length == iod.length_target, (
            f"internode born at {iod.birth_time}: length={iod.length}, "
            f"target={iod.length_target}"
        )


def test_each_bud_emits_at_most_one_internode_per_iteration(tmp_path):
    from palubicki.config import Config, EnvelopeConfig, SimConfig
    from palubicki.sim.simulator import simulate
    cfg = Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=400),
        sim=SimConfig(max_simulation_years=1.0, shoot_extension_max=0.3, vigor_ref=1.0,
                      vigor_dormancy=0.5),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False), geom=GeomConfig(),
        seed=7, output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)
    assert len(tree.all_internodes) <= 2


def test_internode_records_vigor(tmp_path):
    from palubicki.config import Config, EnvelopeConfig, SimConfig
    from palubicki.sim.simulator import simulate
    cfg = Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=600),
        sim=SimConfig(max_simulation_years=8.0, shoot_extension_max=0.3, vigor_ref=1.0,
                      vigor_dormancy=0.5),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False), geom=GeomConfig(),
        seed=7, output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)
    assert tree.all_internodes
    assert all(iod.vigor > 0 for iod in tree.all_internodes)


def test_length_scales_with_vigor(tmp_path):
    from palubicki.config import Config, EnvelopeConfig, SimConfig
    from palubicki.sim.diagnostics import _axis_orders, _walk_internodes
    from palubicki.sim.simulator import simulate
    cfg = Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=1.0, ry=3.0, rz=1.0, marker_count=4000),
        sim=SimConfig(max_simulation_years=20.0, shoot_extension_max=0.3, vigor_ref=1.0,
                      vigor_dormancy=0.5),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False), geom=GeomConfig(),
        seed=7, output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)
    iods = _walk_internodes(tree.root)
    orders = _axis_orders(tree.root)
    order0 = [iod.length_target for iod in iods if orders[id(iod)] == 0]
    high = max(orders.values())
    distal = [iod.length_target for iod in iods if orders[id(iod)] == high]
    assert order0 and distal
    assert (sum(order0) / len(order0)) > (sum(distal) / len(distal))


def _position_signature(forest):
    """Order-independent structural signature of a forest's node positions."""
    import numpy as np
    sig = []
    for ti, tree in enumerate(forest.trees):
        stack = [tree.root]
        while stack:
            node = stack.pop()
            sig.append((ti, tuple(np.round(node.position, 6).tolist())))
            for iod in node.children_internodes:
                stack.append(iod.child_node)
    return sorted(sig)


def test_collector_does_not_perturb_evolution(tmp_path):
    from palubicki.config import load_config
    from palubicki.sim.debug_capture import DebugCollector
    from palubicki.sim.simulator import simulate_forest
    overrides = {
        "envelope.shape": "ellipsoid", "envelope.rx": 1.0, "envelope.ry": 2.0,
        "envelope.rz": 1.0, "envelope.marker_count": 200,
        "sim.max_simulation_years": 5, "seed": 3,
    }
    cfg = load_config(yaml_path=None, cli_overrides=overrides, output=tmp_path / "a.glb")
    plain = simulate_forest(cfg)
    cfg2 = load_config(yaml_path=None, cli_overrides=overrides, output=tmp_path / "b.glb")
    captured = simulate_forest(cfg2, collector=DebugCollector())
    assert _position_signature(plain) == _position_signature(captured)


def test_collector_captures_one_frame_per_executed_iteration(tmp_path):
    from palubicki.config import load_config
    from palubicki.sim.debug_capture import DebugCollector
    from palubicki.sim.simulator import simulate_forest
    cfg = load_config(
        yaml_path=None,
        cli_overrides={"envelope.marker_count": 200, "sim.max_simulation_years": 5, "seed": 3},
        output=tmp_path / "c.glb",
    )
    c = DebugCollector()
    simulate_forest(cfg, collector=c)
    tl = c.timeline()
    assert len(tl["frames"]) >= 1
    # Frame times are non-decreasing.
    times = [f["t"] for f in tl["frames"]]
    assert times == sorted(times)


def test_every_node_emits_leaves(tmp_path):
    from palubicki.config import load_config
    from palubicki.sim.simulator import simulate
    from palubicki.sim.tree import LeafState
    cfg = load_config(
        yaml_path=None,
        cli_overrides={"envelope.marker_count": 200, "sim.max_simulation_years": 5,
                       "seed": 3, "geom.leaf_cluster_count": 3},
        output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)
    n_nodes = 0
    stack = [tree.root]
    while stack:
        node = stack.pop()
        if node.parent_internode is not None:
            n_nodes += 1
            assert len(node.leaves) == 3
            assert all(lf.state is LeafState.ACTIVE for lf in node.leaves)
            assert all(lf.birth_time >= 0.0 for lf in node.leaves)
        for iod in node.children_internodes:
            stack.append(iod.child_node)
    assert n_nodes > 0
    assert len(list(tree.all_leaves())) == n_nodes * 3


def test_enable_leaves_false_emits_no_leaves(tmp_path):
    from palubicki.config import load_config
    from palubicki.sim.simulator import simulate
    cfg = load_config(
        yaml_path=None,
        cli_overrides={"envelope.marker_count": 200, "sim.max_simulation_years": 5,
                       "seed": 3, "geom.enable_leaves": False},
        output=tmp_path / "t.glb",
    )
    tree = simulate(cfg)
    assert list(tree.all_leaves()) == []


def test_leaves_do_not_perturb_skeleton(tmp_path):
    import numpy as np

    from palubicki.config import load_config
    from palubicki.sim.simulator import simulate

    def sig(tree):
        out = []
        stack = [tree.root]
        while stack:
            node = stack.pop()
            out.append(tuple(np.round(node.position, 6).tolist()))
            for iod in node.children_internodes:
                stack.append(iod.child_node)
        return sorted(out)

    base = {"envelope.marker_count": 200, "sim.max_simulation_years": 5, "seed": 3}
    on = simulate(load_config(yaml_path=None, cli_overrides={**base, "geom.enable_leaves": True}, output=tmp_path / "a.glb"))
    off = simulate(load_config(yaml_path=None, cli_overrides={**base, "geom.enable_leaves": False}, output=tmp_path / "b.glb"))
    assert sig(on) == sig(off)
