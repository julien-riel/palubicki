import numpy as np

from palubicki.config import SympodialConfig
from palubicki.sim.sympodial import promote_lateral_if_failing
from palubicki.sim.tree import Bud, BudState, Node, Tree


def _make_node_with_terminal_and_laterals(n_laterals: int = 2):
    node = Node(position=np.zeros(3))
    term = Bud(
        position=np.zeros(3),
        direction=np.array([0.0, 1.0, 0.0]),
        axis_order=0,
        parent_node=node,
    )
    node.terminal_bud = term
    laterals = []
    for _ in range(n_laterals):
        lat = Bud(
            position=np.zeros(3),
            direction=np.array([1.0, 0.0, 0.0]),
            axis_order=1,
            parent_node=node,
        )
        node.lateral_buds.append(lat)
        laterals.append(lat)
    tree = Tree(root=node, active_buds=[term] + laterals)
    return tree, node, term, laterals


def test_promote_skipped_when_disabled():
    tree, node, term, lats = _make_node_with_terminal_and_laterals()
    quality = {term: 0.0, lats[0]: 5.0, lats[1]: 3.0}
    cfg = SympodialConfig(enabled=False, q_threshold=1.0, n_consecutive_steps=1)
    n = promote_lateral_if_failing(tree, quality, cfg)
    assert n == 0
    assert node.terminal_bud is term
    assert term.low_quality_steps == 0


def test_low_quality_counter_increments():
    tree, node, term, lats = _make_node_with_terminal_and_laterals(n_laterals=0)
    quality = {term: 0.5}
    cfg = SympodialConfig(enabled=True, q_threshold=1.0, n_consecutive_steps=10)
    promote_lateral_if_failing(tree, quality, cfg)
    assert term.low_quality_steps == 1
    promote_lateral_if_failing(tree, quality, cfg)
    assert term.low_quality_steps == 2


def test_counter_resets_on_recovery():
    tree, node, term, lats = _make_node_with_terminal_and_laterals(n_laterals=0)
    cfg = SympodialConfig(enabled=True, q_threshold=1.0, n_consecutive_steps=10)
    promote_lateral_if_failing(tree, {term: 0.5}, cfg)
    promote_lateral_if_failing(tree, {term: 0.5}, cfg)
    assert term.low_quality_steps == 2
    promote_lateral_if_failing(tree, {term: 2.0}, cfg)  # recover
    assert term.low_quality_steps == 0


def test_promotion_picks_highest_q_lateral():
    tree, node, term, lats = _make_node_with_terminal_and_laterals(n_laterals=3)
    quality = {term: 0.0, lats[0]: 1.0, lats[1]: 5.0, lats[2]: 3.0}
    cfg = SympodialConfig(enabled=True, q_threshold=1.0, n_consecutive_steps=1)
    n = promote_lateral_if_failing(tree, quality, cfg)
    assert n == 1
    assert node.terminal_bud is lats[1]


def test_promotion_swaps_terminal_in_parent():
    tree, node, term, lats = _make_node_with_terminal_and_laterals(n_laterals=2)
    quality = {term: 0.0, lats[0]: 5.0, lats[1]: 1.0}
    cfg = SympodialConfig(enabled=True, q_threshold=1.0, n_consecutive_steps=1)
    promote_lateral_if_failing(tree, quality, cfg)
    assert node.terminal_bud is lats[0]
    assert lats[0] not in node.lateral_buds
    assert term.state is BudState.DEAD
    assert term not in tree.active_buds


def test_promoted_lateral_inherits_axis_order():
    tree, node, term, lats = _make_node_with_terminal_and_laterals(n_laterals=1)
    quality = {term: 0.0, lats[0]: 5.0}
    cfg = SympodialConfig(enabled=True, q_threshold=1.0, n_consecutive_steps=1)
    assert lats[0].axis_order == 1
    assert term.axis_order == 0
    promote_lateral_if_failing(tree, quality, cfg)
    assert lats[0].axis_order == 0
    assert lats[0].low_quality_steps == 0


def test_no_promotion_without_lateral_candidate():
    tree, node, term, lats = _make_node_with_terminal_and_laterals(n_laterals=0)
    quality = {term: 0.0}
    cfg = SympodialConfig(enabled=True, q_threshold=1.0, n_consecutive_steps=1)
    n = promote_lateral_if_failing(tree, quality, cfg)
    assert n == 0
    assert node.terminal_bud is term
    assert term.state is BudState.ACTIVE


def test_no_promotion_when_laterals_all_zero_quality():
    tree, node, term, lats = _make_node_with_terminal_and_laterals(n_laterals=2)
    quality = {term: 0.0, lats[0]: 0.0, lats[1]: 0.0}
    cfg = SympodialConfig(enabled=True, q_threshold=1.0, n_consecutive_steps=1)
    n = promote_lateral_if_failing(tree, quality, cfg)
    assert n == 0
    assert node.terminal_bud is term


def test_promotion_skipped_until_consecutive_threshold():
    tree, node, term, lats = _make_node_with_terminal_and_laterals(n_laterals=1)
    cfg = SympodialConfig(enabled=True, q_threshold=1.0, n_consecutive_steps=3)
    quality = {term: 0.0, lats[0]: 5.0}
    promote_lateral_if_failing(tree, quality, cfg)
    promote_lateral_if_failing(tree, quality, cfg)
    assert node.terminal_bud is term
    n = promote_lateral_if_failing(tree, quality, cfg)
    assert n == 1
    assert node.terminal_bud is lats[0]
