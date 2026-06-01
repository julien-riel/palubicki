"""Acceptance for #61: leaf caducity (age/season -> LeafState transitions).

Unit tests drive the pure state machine directly (fast, deterministic); a small
integration block runs the full simulator to prove the wiring + the renderer
filter that makes abscised leaves vanish from the mesh.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from palubicki.config import LeafPhenologyConfig, load_config
from palubicki.geom.leaves import selected_leaves
from palubicki.sim.caducity import advance_leaf_states
from palubicki.sim.simulator import simulate
from palubicki.sim.tree import Bud, BudState, Leaf, LeafState, Node, Tree


def _leafy_tree(*, birth_time=0.0, n_leaves=1):
    """A one-node tree carrying ``n_leaves`` ACTIVE leaves, with an active apex
    bud so ``selected_leaves`` will pick the node up."""
    root = Node(position=np.zeros(3))
    root.leaves = [
        Leaf(parent_node=root, azimuth=0.0, birth_time=birth_time)
        for _ in range(n_leaves)
    ]
    bud = Bud(
        position=np.zeros(3), direction=np.array([0.0, 1.0, 0.0]),
        axis_order=0, parent_node=root, state=BudState.ACTIVE,
    )
    return Tree(root=root, active_buds=[bud])


def _cfg(*, deciduous, lifespan=2.0, senescence=0.1, window=(0.0, 0.5)):
    return SimpleNamespace(sim=SimpleNamespace(
        leaf_phenology=LeafPhenologyConfig(
            enabled=True, deciduous=deciduous,
            leaf_lifespan_years=lifespan, senescence_duration_years=senescence,
        ),
        annual_growth_period=window,
    ))


def _states(tree):
    return [lf.state for lf in tree.all_leaves()]


# --- pure state machine -----------------------------------------------------

def test_disabled_never_transitions():
    tree = _leafy_tree()
    forest = SimpleNamespace(trees=[tree])
    cfg = _cfg(deciduous=True)
    cfg.sim.leaf_phenology = LeafPhenologyConfig(enabled=False, deciduous=True)
    for k in range(20):
        advance_leaf_states(forest, cfg, t=k * 0.25)
    assert _states(tree) == [LeafState.ACTIVE]


def test_deciduous_sheds_on_dormant_entry_and_abscises():
    tree = _leafy_tree(birth_time=0.0)
    forest = SimpleNamespace(trees=[tree])
    cfg = _cfg(deciduous=True, lifespan=10.0, senescence=0.1, window=(0.0, 0.5))
    leaf = tree.root.leaves[0]

    # In the growth window: stays ACTIVE.
    advance_leaf_states(forest, cfg, t=0.25)
    assert leaf.state is LeafState.ACTIVE

    # First dormant step (frac 0.5 >= window hi): senesces.
    advance_leaf_states(forest, cfg, t=0.5)
    assert leaf.state is LeafState.SENESCENT
    assert leaf.senescence_time == 0.5

    # senescence_duration elapsed -> abscises.
    advance_leaf_states(forest, cfg, t=0.75)
    assert leaf.state is LeafState.ABSCISSED


def test_deciduous_regrows_next_window():
    """Old leaves abscise in the dormant window; a leaf emitted in the next
    growth window stays ACTIVE — the regrowth half of acceptance criterion 1."""
    tree = _leafy_tree(birth_time=0.0)
    forest = SimpleNamespace(trees=[tree])
    cfg = _cfg(deciduous=True, lifespan=10.0, senescence=0.1, window=(0.0, 0.5))

    for t in (0.0, 0.25, 0.5, 0.75):
        advance_leaf_states(forest, cfg, t=t)
    assert all(s is not LeafState.ACTIVE for s in _states(tree))  # all shed

    # Next growth window: a freshly emitted leaf survives.
    new_leaf = Leaf(parent_node=tree.root, azimuth=1.0, birth_time=1.0)
    tree.root.leaves.append(new_leaf)
    advance_leaf_states(forest, cfg, t=1.0)
    assert new_leaf.state is LeafState.ACTIVE


def test_evergreen_persists_across_year_boundary():
    """Evergreen leaf survives a year boundary, sheds only past lifespan."""
    tree = _leafy_tree(birth_time=0.2)
    forest = SimpleNamespace(trees=[tree])
    cfg = _cfg(deciduous=False, lifespan=1.5, senescence=0.1, window=(0.0, 0.5))
    leaf = tree.root.leaves[0]

    # Crosses t=1.0 (year boundary) still ACTIVE — dormant window does not shed
    # an evergreen leaf.
    for t in (0.45, 0.7, 1.0, 1.2, 1.45):
        advance_leaf_states(forest, cfg, t=t)
        assert leaf.state is LeafState.ACTIVE, f"shed early at t={t}"

    # age = 1.7 - 0.2 = 1.5 >= lifespan -> senesces.
    advance_leaf_states(forest, cfg, t=1.7)
    assert leaf.state is LeafState.SENESCENT


def test_deterministic_pure_function_of_age():
    """Same inputs -> same transition schedule, no RNG."""
    schedules = []
    for _ in range(2):
        tree = _leafy_tree(birth_time=0.0)
        forest = SimpleNamespace(trees=[tree])
        cfg = _cfg(deciduous=True, lifespan=3.0, senescence=0.1)
        seq = []
        for k in range(12):
            advance_leaf_states(forest, cfg, t=k * 0.25)
            seq.append(tree.root.leaves[0].state)
        schedules.append(seq)
    assert schedules[0] == schedules[1]


# --- renderer filter (acceptance criterion 3) -------------------------------

def test_abscised_leaf_drops_out_of_selected_leaves():
    tree = _leafy_tree(n_leaves=1)
    leaf = tree.root.leaves[0]

    assert len(selected_leaves(tree, foliage_depth=1)) == 1
    leaf.state = LeafState.ABSCISSED
    assert selected_leaves(tree, foliage_depth=1) == []
    leaf.state = LeafState.SENESCENT  # senescent is also off the ACTIVE roster
    assert selected_leaves(tree, foliage_depth=1) == []


# --- end-to-end wiring through the simulator --------------------------------

pytestmark_slow = pytest.mark.slow


def _run(tmp_path, *, deciduous, lifespan, years=4.0, dt=0.25, window=(0.0, 0.5),
         out_name="o.glb"):
    cfg = load_config(
        yaml_path=None,
        cli_overrides={
            "sim.dt_years": dt,
            "sim.max_simulation_years": years,
            "sim.annual_growth_period": list(window),
            "sim.leaf_phenology.enabled": True,
            "sim.leaf_phenology.deciduous": deciduous,
            "sim.leaf_phenology.leaf_lifespan_years": lifespan,
            "sim.leaf_phenology.senescence_duration_years": 0.1,
            "envelope.marker_count": 1500,
            "seed": 0,
        },
        output=tmp_path / out_name,
    )
    return simulate(cfg)


@pytest.mark.slow
def test_integration_deciduous_drops_all_active_in_dormant_window(tmp_path):
    # years=4.0, dt=0.25 -> last step t=3.75 (frac 0.75, dormant). All leaves
    # should be off the ACTIVE roster, but some leaves were emitted (so the tree
    # genuinely grew then shed, not "never had leaves").
    tree = _run(tmp_path, deciduous=True, lifespan=10.0)
    leaves = list(tree.all_leaves())
    assert leaves, "expected the tree to have emitted leaves"
    active = [lf for lf in leaves if lf.state is LeafState.ACTIVE]
    assert active == [], f"{len(active)} leaves still ACTIVE in dormant window"
    assert any(lf.state is LeafState.ABSCISSED for lf in leaves)


@pytest.mark.slow
def test_integration_evergreen_retains_with_long_lifespan(tmp_path):
    # Lifespan >> sim duration: an evergreen never sheds, even across year
    # boundaries and through dormant windows.
    tree = _run(tmp_path, deciduous=False, lifespan=100.0)
    leaves = list(tree.all_leaves())
    assert leaves
    assert all(lf.state is LeafState.ACTIVE for lf in leaves)


@pytest.mark.slow
def test_integration_deterministic(tmp_path):
    a = _run(tmp_path, deciduous=True, lifespan=2.0, out_name="a.glb")
    b = _run(tmp_path, deciduous=True, lifespan=2.0, out_name="b.glb")
    assert _states(a) == _states(b)
