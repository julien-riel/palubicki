import numpy as np

from palubicki.sim.tree import Leaf, LeafState, Node, Tree


def test_leafstate_has_three_members():
    assert {s.name for s in LeafState} == {"ACTIVE", "SENESCENT", "ABSCISSED"}


def test_node_leaves_defaults_empty():
    n = Node(position=np.zeros(3))
    assert n.leaves == []


def test_leaf_position_is_derived_and_tracks_node():
    n = Node(position=np.array([1.0, 2.0, 3.0]))
    n.sag_offset = np.array([0.0, -0.5, 0.0])
    leaf = Leaf(parent_node=n, azimuth=0.0, birth_time=1.0)
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
    root = Node(position=np.zeros(3))
    leaf = Leaf(parent_node=root, azimuth=0.0, birth_time=0.0)
    root.leaves.append(leaf)
    tree = Tree(root=root)
    assert list(tree.all_leaves()) == [leaf]
