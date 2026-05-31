import math

import numpy as np

from palubicki.config import PhyllotaxyConfig
from palubicki.sim.phyllotaxy import leaf_azimuths
from palubicki.sim.tree import Leaf, LeafState, Node, Tree


def test_leafstate_has_three_members():
    assert {s.name for s in LeafState} == {"ACTIVE", "SENESCENT", "ABSCISSED"}


def test_node_leaves_defaults_empty():
    n = Node(position=np.zeros(3))
    assert n.leaves == []


def test_leaf_position_is_derived_and_tracks_node():
    # Default sag_offset is zeros -> leaf sits exactly at the node.
    n = Node(position=np.array([1.0, 2.0, 3.0]))
    leaf = Leaf(parent_node=n, azimuth=0.0, birth_time=1.0)
    assert np.allclose(leaf.position, [1.0, 2.0, 3.0])
    # With a sag offset, position includes it.
    n.sag_offset = np.array([0.0, -0.5, 0.0])
    assert np.allclose(leaf.position, [1.0, 1.5, 3.0])
    # Moving the node moves the leaf (no frozen world coordinate).
    n.position = np.array([10.0, 0.0, 0.0])
    assert np.allclose(leaf.position, [10.0, -0.5, 0.0])
    assert leaf.state is LeafState.ACTIVE


def test_leaf_age_uses_clock():
    from palubicki.sim.clock import Clock
    n = Node(position=np.zeros(3))
    leaf = Leaf(parent_node=n, azimuth=0.0, birth_time=2.0)
    clock = Clock(dt=1.0)
    clock.t = 5.0
    assert leaf.age(clock) == 3.0


def test_tree_all_leaves_walks_graph():
    from palubicki.sim.tree import Internode
    root = Node(position=np.zeros(3))
    child = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=root, child_node=child, length=1.0, is_main_axis=True)
    root.children_internodes.append(iod)
    child.parent_internode = iod
    lr = Leaf(parent_node=root, azimuth=0.0, birth_time=0.0)
    lc = Leaf(parent_node=child, azimuth=1.0, birth_time=1.0)
    root.leaves.append(lr)
    child.leaves.append(lc)
    tree = Tree(root=root)
    assert set(map(id, tree.all_leaves())) == {id(lr), id(lc)}


def test_leaf_azimuths_returns_count_floats():
    cfg = PhyllotaxyConfig(mode="alternate", divergence_angle_deg=137.5)
    az = leaf_azimuths(cfg, node_index=0, axis_order=0, count=3)
    assert len(az) == 3
    assert all(isinstance(a, float) for a in az)
    # count members fanned evenly 2*pi/count apart from the base.
    assert math.isclose(az[1] - az[0], 2 * math.pi / 3, rel_tol=1e-9)
    assert math.isclose(az[2] - az[1], 2 * math.pi / 3, rel_tol=1e-9)


def test_leaf_azimuths_advance_with_ordinal():
    cfg = PhyllotaxyConfig(mode="alternate", divergence_angle_deg=137.5)
    a0 = leaf_azimuths(cfg, node_index=0, axis_order=0, count=1)[0]
    a1 = leaf_azimuths(cfg, node_index=1, axis_order=0, count=1)[0]
    assert math.isclose(a1 - a0, math.radians(137.5), rel_tol=1e-9)


def test_leaf_azimuths_distichous_on_plagiotropic_lateral():
    cfg = PhyllotaxyConfig(mode="alternate", distichous_on_plagiotropic=True)
    # axis_order>0 with the flag -> distichous: 180 deg per node.
    a0 = leaf_azimuths(cfg, node_index=0, axis_order=1, count=1)[0]
    a1 = leaf_azimuths(cfg, node_index=1, axis_order=1, count=1)[0]
    assert math.isclose(a1 - a0, math.pi, rel_tol=1e-9)
