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
