import numpy as np

from palubicki.geom.leaves import build_leaves_primitive
from palubicki.geom.mesh import Material
from palubicki.sim.tree import Bud, BudState, Node, Tree


def _mat():
    return Material(name="leaf", base_color=(1, 1, 1, 1), metallic=0.0, roughness=1.0,
                    base_color_texture_png=b"\x89PNG\r\n\x1a\n",
                    alpha_mode="MASK", alpha_cutoff=0.5, double_sided=True)


def _tree_with_n_terminal_buds(n):
    root = Node(position=np.zeros(3))
    tree = Tree(root=root)
    for i in range(n):
        node = Node(position=np.array([float(i), 1.0, 0.0]))
        bud = Bud(position=node.position.copy(), direction=np.array([0.0, 1.0, 0.0]),
                  axis_order=0, parent_node=node, state=BudState.ACTIVE)
        node.terminal_bud = bud
        tree.active_buds.append(bud)
    return tree


def test_one_bud_eight_vertices_twelve_indices():
    tree = _tree_with_n_terminal_buds(1)
    prim = build_leaves_primitive(tree, leaf_size=0.1, material=_mat())
    assert prim.positions.shape == (8, 3)
    assert prim.indices.shape == (12,)


def test_dead_buds_excluded():
    tree = _tree_with_n_terminal_buds(1)
    tree.active_buds[0].state = BudState.DEAD
    prim = build_leaves_primitive(tree, leaf_size=0.1, material=_mat())
    assert prim.positions.shape == (0, 3)


def test_three_buds_yields_24_vertices():
    tree = _tree_with_n_terminal_buds(3)
    prim = build_leaves_primitive(tree, leaf_size=0.1, material=_mat())
    assert prim.positions.shape == (24, 3)
    assert prim.indices.shape == (36,)


def test_indices_within_bounds():
    tree = _tree_with_n_terminal_buds(2)
    prim = build_leaves_primitive(tree, leaf_size=0.1, material=_mat())
    assert prim.indices.max() < prim.positions.shape[0]
