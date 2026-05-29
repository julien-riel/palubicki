import pytest
import numpy as np

from palubicki.sim.bh import allocate
from palubicki.sim.tree import Bud, Internode, Node, Tree


def _single_bud_tree(direction=(0, 1, 0)):
    root = Node(position=np.zeros(3))
    bud = Bud(position=np.zeros(3), direction=np.array(direction, dtype=float),
              axis_order=0, parent_node=root)
    root.terminal_bud = bud
    tree = Tree(root=root, active_buds=[bud])
    return tree, bud


def test_single_bud_n_equals_alpha_times_q():
    tree, bud = _single_bud_tree()
    quality = {bud: 4}
    n_by_bud = allocate(tree, quality=quality, alpha=2.0, lambda_apical=0.5)
    assert n_by_bud[bud] == pytest.approx(8.0)


def test_zero_quality_yields_zero_growth():
    tree, bud = _single_bud_tree()
    quality = {bud: 0}
    n_by_bud = allocate(tree, quality=quality, alpha=2.0, lambda_apical=0.5)
    assert n_by_bud[bud] == pytest.approx(0.0)


def test_split_main_lateral_with_lambda():
    # Build: root -> internode -> child_node with main_bud + lateral_bud
    root = Node(position=np.zeros(3))
    child = Node(position=np.array([0, 1, 0], dtype=float))
    iod = Internode(parent_node=root, child_node=child, length=1.0, is_main_axis=True)
    root.children_internodes.append(iod)
    child.parent_internode = iod
    main_bud = Bud(position=child.position, direction=np.array([0, 1, 0]),
                   axis_order=0, parent_node=child)
    lat_bud = Bud(position=child.position, direction=np.array([1, 0, 0]),
                  axis_order=1, parent_node=child)
    child.terminal_bud = main_bud
    child.lateral_buds.append(lat_bud)
    tree = Tree(root=root, active_buds=[main_bud, lat_bud], all_internodes=[iod])
    quality = {main_bud: 4, lat_bud: 2}
    n_by_bud = allocate(tree, quality=quality, alpha=1.0, lambda_apical=0.7)
    # v_root = Q_main + Q_lat = 6; v_total = alpha * 6 = 6
    # v_main = 6 * (0.7*4)/(0.7*4 + 0.3*2) = 6 * 2.8/3.4 = 4.941...
    # v_lat = 6 - 4.941 = 1.058...
    assert n_by_bud[main_bud] == pytest.approx(4.9411764, rel=1e-5)
    assert n_by_bud[lat_bud] == pytest.approx(1.0588235, rel=1e-5)
    assert n_by_bud[main_bud] + n_by_bud[lat_bud] == pytest.approx(6.0)


def test_zero_split_when_both_qualities_zero():
    root = Node(position=np.zeros(3))
    child = Node(position=np.array([0, 1, 0], dtype=float))
    iod = Internode(parent_node=root, child_node=child, length=1.0, is_main_axis=True)
    root.children_internodes.append(iod)
    child.parent_internode = iod
    m = Bud(position=child.position, direction=np.array([0, 1, 0]), axis_order=0, parent_node=child)
    lat = Bud(position=child.position, direction=np.array([1, 0, 0]), axis_order=1, parent_node=child)
    child.terminal_bud = m
    child.lateral_buds.append(lat)
    tree = Tree(root=root, active_buds=[m, lat], all_internodes=[iod])
    n_by_bud = allocate(tree, quality={m: 0, lat: 0}, alpha=2.0, lambda_apical=0.5)
    assert n_by_bud[m] == pytest.approx(0.0) and n_by_bud[lat] == pytest.approx(0.0)


def test_denom_zero_proportional_fallback():
    # lam=0 means only laterals count in denom; if terminal has 0 quality and
    # laterals have quality, denom = 0*q_m + 1*q_l > 0, not this path.
    # denom=0 when lam=0 and q_l=0 but total_q>0 → only terminal has quality.
    # lam=0 → denom = 0*q_m + 1*0 = 0, but total_q = q_m > 0 → triggers fallback.
    root = Node(position=np.zeros(3))
    bud = Bud(position=np.zeros(3), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=root)
    root.terminal_bud = bud
    tree = Tree(root=root, active_buds=[bud])
    quality = {bud: 5}
    # lambda_apical=0 makes denom = 0*5 + 1*0 = 0 with only terminal bud
    # total_q=5>0 so we enter proportional fallback: v_here * 5 / 5 = v_here
    n_by_bud = allocate(tree, quality=quality, alpha=1.0, lambda_apical=0.0)
    # v_total = alpha * 5 = 5; proportional: 5 * 5/5 = 5.0
    assert n_by_bud[bud] == pytest.approx(5.0)


def test_fractional_flux_is_not_floored():
    tree, bud = _single_bud_tree()
    quality = {bud: 1}
    n_by_bud = allocate(tree, quality=quality, alpha=1.5, lambda_apical=0.5)
    # v_b = 1.5 — must NOT be floored to 1
    assert n_by_bud[bud] == pytest.approx(1.5)
