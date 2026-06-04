"""Unit tests for the shadow-propagation exposure engine (#56), on small
hand-filled / hand-deposited grids — no simulation. Phase 2: the LightGrid
shadow field, pyramid deposition, per-bud exposure Q, and the light gradient."""
from __future__ import annotations

import numpy as np
import pytest

from palubicki.config import EnvelopeConfig, LightConfig, ShadowConfig
from palubicki.sim.light import LightGrid, _fib_hemisphere


def _grid(n: int = 10, size: float = 1.0) -> LightGrid:
    """A clean axis-aligned grid: origin (0,0,0), cube `size`, `n` cells/axis.
    With n=10, size=1 → cell_size 0.1 and cell (i,j,k) center = (i+0.5)*0.1."""
    cfg = LightConfig(
        grid_origin=(0.0, 0.0, 0.0),
        grid_size=(size, size, size),
        grid_resolution=(n, n, n),
    )
    return LightGrid.from_config(cfg, EnvelopeConfig())


def test_shadow_field_allocated_and_zeroed():
    g = _grid()
    assert g.shadow.shape == (10, 10, 10)
    assert g.shadow.dtype == np.float32
    assert g.shadow.sum() == 0.0


def test_deposit_shadow_pyramid_footprint_and_decay():
    """A single organ stamps the Palubicki index set (I±p, J−q, K±p) with
    Δs = a·b**(−q)."""
    g = _grid()
    cfg = ShadowConfig(a=1.0, b=2.0, q_max=2, area_weight=1.0)
    pos = g.cell_to_world_center(5, 5, 5)
    g._deposit_shadow(np.array([pos]), np.array([1.0]), cfg)

    # q=0: the organ's own cell only, Δs = a = 1.0
    assert g.shadow[5, 5, 5] == pytest.approx(1.0)
    assert g.shadow[4, 5, 5] == 0.0          # j=5 has no footprint beyond (5,5,5)
    assert g.shadow[5, 6, 5] == 0.0          # nothing ABOVE the organ

    # q=1: j=4, 3×3 footprint over i,k ∈ [4,6], Δs = a·b^-1 = 0.5
    assert g.shadow[5, 4, 5] == pytest.approx(0.5)
    assert g.shadow[4, 4, 6] == pytest.approx(0.5)
    assert g.shadow[3, 4, 5] == 0.0          # outside the 3×3 at q=1

    # q=2: j=3, 5×5 footprint over i,k ∈ [3,7], Δs = a·b^-2 = 0.25
    assert g.shadow[3, 3, 3] == pytest.approx(0.25)
    assert g.shadow[7, 3, 7] == pytest.approx(0.25)
    assert g.shadow[2, 3, 5] == 0.0          # outside the 5×5 at q=2


def test_deposit_shadow_area_weight_and_floor_break():
    """Δs scales with area·area_weight; the pyramid stops at the grid floor."""
    g = _grid()
    cfg = ShadowConfig(a=1.0, b=2.0, q_max=5, area_weight=2.0)
    pos = g.cell_to_world_center(5, 1, 5)        # only one layer above the floor
    g._deposit_shadow(np.array([pos]), np.array([3.0]), cfg)

    w = 3.0 * 2.0                                 # area · area_weight = 6
    assert g.shadow[5, 1, 5] == pytest.approx(w * 1.0)     # q=0
    assert g.shadow[5, 0, 5] == pytest.approx(w * 0.5)     # q=1 → j=0
    # q≥2 would write j<0 → broken out of; nothing crashes, nothing below 0.
    assert g.shadow.min() >= 0.0


def test_exposure_unshaded_reads_full_light_and_zero_gradient():
    g = _grid()
    cfg = ShadowConfig(a=1.0, full_light_C=1.0)
    pos = g.cell_to_world_center(5, 5, 5)
    Q, grad = g.sample_exposure_batch(
        np.array([pos]), np.array([[0.0, 1.0, 0.0]]),
        cfg=cfg, r_perception=0.3,
    )
    assert Q[0] == pytest.approx(1.0)                       # no shadow → full light
    assert np.linalg.norm(grad[0]) == pytest.approx(0.0)   # uniform → no preference


def test_exposure_self_cancel_clamp_and_monotone():
    """Q = min(C, max(0, C − s + a)): unshaded (s ≤ a) reads C; heavy shade drops
    monotonically toward 0."""
    g = _grid()
    cfg = ShadowConfig(a=1.0, full_light_C=1.0)
    cell = (5, 5, 5)
    pos = g.cell_to_world_center(*cell)
    args = dict(cfg=cfg, r_perception=0.0)
    up = np.array([[0.0, 1.0, 0.0]])

    g.shadow[cell] = 1.0                          # self-stamp exactly a → Q == C
    assert g.sample_exposure_batch(np.array([pos]), up, **args)[0][0] == pytest.approx(1.0)

    g.shadow[cell] = 0.5                          # below a → still clamped to C
    assert g.sample_exposure_batch(np.array([pos]), up, **args)[0][0] == pytest.approx(1.0)

    g.shadow[cell] = 1.5                          # above a → 1 − 1.5 + 1 = 0.5
    q_mid = g.sample_exposure_batch(np.array([pos]), up, **args)[0][0]
    g.shadow[cell] = 5.0                          # max(0, 1 − 5 + 1) = 0
    q_dark = g.sample_exposure_batch(np.array([pos]), up, **args)[0][0]
    assert q_mid == pytest.approx(0.5)
    assert q_dark == pytest.approx(0.0)
    assert q_dark < q_mid < 1.0


def test_exposure_offgrid_bud_reads_full_light():
    g = _grid()
    cfg = ShadowConfig(a=1.0, full_light_C=1.0)
    pos = np.array([5.0, 5.0, 5.0])               # far outside the unit grid
    Q, _ = g.sample_exposure_batch(
        np.array([pos]), np.array([[0.0, 1.0, 0.0]]), cfg=cfg, r_perception=0.1,
    )
    assert Q[0] == pytest.approx(1.0)


def test_exposure_gradient_points_to_brighter_side():
    """Shadow the +x half of the grid; an upward-heading bud's gradient leans −x
    (toward the open side)."""
    g = _grid()
    cfg = ShadowConfig(a=1.0, full_light_C=1.0)
    g.shadow[6:, :, :] = 10.0                      # +x half fully dark
    pos = g.cell_to_world_center(5, 5, 5)
    Q, grad = g.sample_exposure_batch(
        np.array([pos]), np.array([[0.0, 1.0, 0.0]]),  # heading up → spreads in x/z
        cfg=cfg, r_perception=0.3,
    )
    assert np.linalg.norm(grad[0]) == pytest.approx(1.0)   # normalized
    assert grad[0][0] < 0.0                                # toward −x (the lit side)


def test_zero_heading_yields_zero_gradient():
    g = _grid()
    cfg = ShadowConfig(a=1.0, full_light_C=1.0)
    g.shadow[6:, :, :] = 10.0
    pos = g.cell_to_world_center(5, 5, 5)
    _, grad = g.sample_exposure_batch(
        np.array([pos]), np.array([[0.0, 0.0, 0.0]]), cfg=cfg, r_perception=0.3,
    )
    assert np.linalg.norm(grad[0]) == 0.0


def test_fib_hemisphere_is_forward_unit_set():
    d = _fib_hemisphere(16)
    assert d.shape == (16, 3)
    assert np.allclose(np.linalg.norm(d, axis=1), 1.0)
    assert (d[:, 2] > 0).all()                     # every direction forward (+Z)


def test_perceive_exposure_wraps_batch_into_struct():
    from palubicki.sim.light_perception import perceive_exposure
    from palubicki.sim.tree import Bud, Node

    g = _grid()
    cfg = ShadowConfig(a=1.0, full_light_C=2.0)
    root = Node(position=np.zeros(3))
    bud = Bud(
        position=g.cell_to_world_center(5, 5, 5),
        direction=np.array([0.0, 1.0, 0.0]),
        axis_order=0,
        parent_node=root,
    )
    res = perceive_exposure([bud], g, cfg, r_perception=0.3)
    assert res.exposure[bud] == pytest.approx(2.0)         # unshaded → C
    assert res.light_factor[bud] == pytest.approx(1.0)     # Q / C
    assert bud in res.gradient

    # Empty input is a no-op.
    empty = perceive_exposure([], g, cfg, r_perception=0.3)
    assert empty.exposure == {} and empty.gradient == {}
