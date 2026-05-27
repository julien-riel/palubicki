import numpy as np

from palubicki.sim.tree import Bud, BudState, Internode, Node, Tree


def test_tree_construction_root_only():
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    bud = Bud(position=root.position, direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=root)
    root.terminal_bud = bud
    tree = Tree(root=root)
    tree.active_buds.append(bud)
    assert tree.root is root
    assert len(tree.all_internodes) == 0
    assert tree.active_buds == [bud]


def test_bud_default_state_active():
    bud = Bud(position=np.zeros(3), direction=np.array([0, 1, 0]),
              axis_order=0, parent_node=Node(position=np.zeros(3)))
    assert bud.state == BudState.ACTIVE


def test_quality_history_bounded(qmax=5):
    iod = Internode(parent_node=Node(position=np.zeros(3)),
                    child_node=Node(position=np.array([0, 1, 0])),
                    length=1.0, is_main_axis=True, window=qmax)
    for v in range(10):
        iod.push_quality(float(v))
    assert list(iod.quality_history) == [5.0, 6.0, 7.0, 8.0, 9.0]
    assert iod.average_quality() == 7.0


def test_internode_links_nodes_bidirectionally():
    parent = Node(position=np.zeros(3))
    child = Node(position=np.array([0, 1, 0]))
    iod = Internode(parent_node=parent, child_node=child, length=1.0, is_main_axis=True)
    parent.children_internodes.append(iod)
    child.parent_internode = iod
    assert iod in parent.children_internodes
    assert child.parent_internode is iod


def test_bud_state_has_reserve():
    assert BudState.RESERVE is not None
    assert BudState.RESERVE not in (BudState.ACTIVE, BudState.DORMANT, BudState.DEAD)


def test_bud_default_low_light_steps_is_zero():
    bud = Bud(position=np.zeros(3), direction=np.array([0, 1, 0]),
              axis_order=0, parent_node=Node(position=np.zeros(3)))
    assert bud.low_light_steps == 0


def test_node_default_dormant_reserve_buds_is_empty_list():
    node = Node(position=np.zeros(3))
    assert node.dormant_reserve_buds == []
    other = Node(position=np.zeros(3))
    node.dormant_reserve_buds.append("sentinel")
    assert other.dormant_reserve_buds == []


def test_internode_default_light_factor_one():
    p = Node(position=np.zeros(3))
    c = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=p, child_node=c, length=1.0, is_main_axis=True)
    assert iod.light_factor == 1.0


def test_internode_accepts_explicit_light_factor():
    p = Node(position=np.zeros(3))
    c = Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(
        parent_node=p, child_node=c, length=1.0,
        is_main_axis=True, light_factor=0.42,
    )
    assert iod.light_factor == 0.42


def test_node_sag_offset_defaults_to_zero_vector():
    n = Node(position=np.array([1.0, 2.0, 3.0]))
    np.testing.assert_array_equal(n.sag_offset, np.zeros(3))
    assert n.sag_offset.dtype == np.float64
