# tests/sim/test_shedding.py
import numpy as np

from palubicki.config import SheddingConfig
from palubicki.sim.shedding import record_qualities, shed_low_quality
from palubicki.sim.tree import Bud, BudState, Internode, Node, Tree


def _linear_tree(n):
    root = Node(position=np.zeros(3))
    prev = root
    iods = []
    for i in range(n):
        child = Node(position=np.array([0, float(i + 1), 0]))
        iod = Internode(parent_node=prev, child_node=child, length=1.0, is_main_axis=True, window=3)
        prev.children_internodes.append(iod)
        child.parent_internode = iod
        iods.append(iod)
        prev = child
    bud = Bud(position=prev.position, direction=np.array([0, 1, 0]),
              axis_order=0, parent_node=prev)
    prev.terminal_bud = bud
    return Tree(root=root, active_buds=[bud], all_internodes=iods), bud, iods


def test_record_qualities_pushes_subtree_quality():
    tree, bud, iods = _linear_tree(2)
    record_qualities(tree, quality={bud: 3})
    assert iods[0].quality_history[-1] == 3.0
    assert iods[1].quality_history[-1] == 3.0


def test_shed_removes_low_quality_subtree():
    tree, bud, iods = _linear_tree(3)
    # Fill all internodes with zero quality over the window
    for _ in range(5):
        record_qualities(tree, quality={bud: 0})
    cfg = SheddingConfig(quality_threshold=0.5, window=3, enabled=True)
    shed_low_quality(tree, cfg=cfg)
    assert bud.state == BudState.DEAD
    assert bud not in tree.active_buds


def test_shed_keeps_high_quality_intact():
    tree, bud, iods = _linear_tree(2)
    for _ in range(5):
        record_qualities(tree, quality={bud: 5})
    cfg = SheddingConfig(quality_threshold=0.5, window=3, enabled=True)
    shed_low_quality(tree, cfg=cfg)
    assert bud.state == BudState.ACTIVE
    assert bud in tree.active_buds


def test_shedding_disabled_is_noop():
    tree, bud, iods = _linear_tree(2)
    for _ in range(5):
        record_qualities(tree, quality={bud: 0})
    cfg = SheddingConfig(enabled=False)
    shed_low_quality(tree, cfg=cfg)
    assert bud.state == BudState.ACTIVE


def test_shed_middle_sibling_no_crash():
    """Regression: list.remove on non-first sibling used to crash on numpy ambiguity."""
    root = Node(position=np.zeros(3))
    children = []
    buds = []
    for i in range(3):
        child = Node(position=np.array([float(i), 1.0, 0.0]))
        iod = Internode(parent_node=root, child_node=child, length=1.0, is_main_axis=(i == 0), window=3)
        root.children_internodes.append(iod)
        child.parent_internode = iod
        child_bud = Bud(position=child.position, direction=np.array([0.0, 1.0, 0.0]),
                        axis_order=0, parent_node=child)
        child.terminal_bud = child_bud
        children.append((child, iod))
        buds.append(child_bud)
    tree = Tree(root=root, active_buds=list(buds),
                all_internodes=[iod for _, iod in children])
    # Outer children have high quality; middle has zero so only it sheds.
    quality = {buds[0]: 5, buds[1]: 0, buds[2]: 5}
    for _ in range(5):
        record_qualities(tree, quality=quality)
    cfg = SheddingConfig(quality_threshold=0.5, window=3, enabled=True)
    shed_low_quality(tree, cfg=cfg)
    # Middle internode shed; first and third should remain
    assert len(root.children_internodes) == 2
    assert buds[1].state == BudState.DEAD
    assert buds[0].state == BudState.ACTIVE
    assert buds[2].state == BudState.ACTIVE
