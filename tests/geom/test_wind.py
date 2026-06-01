from pathlib import Path

import numpy as np
import pytest

from palubicki.config import (
    Config,
    EnvelopeConfig,
    GeomConfig,
    PhyllotaxyConfig,
    SheddingConfig,
    SimConfig,
    TropismConfig,
)
from palubicki.geom.builder import build_mesh
from palubicki.geom.wind import (
    WIND_TIER_MAX,
    WindCalibration,
    branch_phase,
    calibrate,
    leaf_phase,
    tier,
)
from palubicki.sim.simulator import simulate

# ── calibration / stiffness ───────────────────────────────────────────────

def test_stiffness_maps_range_to_unit_interval():
    cal = WindCalibration(d_min=0.02, d_max=0.10)
    assert cal.stiffness(0.02) == pytest.approx(0.0)   # thinnest -> fully flexible
    assert cal.stiffness(0.10) == pytest.approx(1.0)   # thickest -> rigid
    assert cal.stiffness(0.06) == pytest.approx(0.5)   # midpoint


def test_stiffness_is_monotonic_and_clamped():
    cal = WindCalibration(d_min=0.02, d_max=0.10)
    xs = np.linspace(0.0, 0.2, 25)
    ys = [cal.stiffness(x) for x in xs]
    assert all(0.0 <= y <= 1.0 for y in ys)
    assert all(b >= a - 1e-9 for a, b in zip(ys, ys[1:], strict=False))  # non-decreasing
    assert cal.stiffness(-1.0) == 0.0
    assert cal.stiffness(99.0) == 1.0


def test_degenerate_span_is_rigid():
    cal = WindCalibration(d_min=0.05, d_max=0.05)
    assert cal.stiffness(0.05) == 1.0
    assert cal.stiffness(0.0) == 1.0


def test_calibrate_reads_tree_diameter_range():
    cfg = _cfg()
    tree = simulate(cfg)
    cal = calibrate(tree)
    assert cal.d_min > 0.0
    assert cal.d_max >= cal.d_min
    # Real internodes sit in the ~cm range; sanity-bound it well clear of nonsense.
    assert cal.d_max < 1.0


# ── tier ──────────────────────────────────────────────────────────────────

def test_tier_clamps_to_zero_two():
    assert tier(0) == 0
    assert tier(1) == 1
    assert tier(2) == 2
    assert tier(5) == WIND_TIER_MAX == 2
    assert tier(-3) == 0


# ── phase: deterministic, bounded, tree-relative ──────────────────────────

def test_branch_phase_bounded_and_deterministic():
    p = np.array([0.3, 1.2, -0.5])
    a = branch_phase(p, 3)
    b = branch_phase(p, 3)
    assert a == b
    assert 0.0 <= a < 1.0


def test_branch_phase_advances_along_axis():
    p = np.array([0.3, 1.2, -0.5])
    # The travelling-wave term makes consecutive ordinals differ.
    assert branch_phase(p, 0) != branch_phase(p, 1)


def test_branch_phase_is_origin_relative():
    # Identical *local* geometry must hash to the same phase regardless of where the
    # tree is placed — this is what lets identical forest trees share one mesh.
    here = branch_phase(np.array([0.0, 5.0, 0.0]), 2)
    shifted = branch_phase(np.array([10.0, 5.0, 3.0]), 2, origin=np.array([10.0, 0.0, 3.0]))
    assert here == pytest.approx(shifted)


def test_leaf_phase_desyncs_by_azimuth():
    pos = np.array([0.1, 0.9, 0.2])
    assert leaf_phase(pos, 0.0) != leaf_phase(pos, 2.0)
    assert 0.0 <= leaf_phase(pos, 1.3) < 1.0


# ── integration: the stamped mesh honors the contract ─────────────────────

def test_built_mesh_stamps_wind_contract():
    cfg = _cfg()
    mesh = build_mesh(simulate(cfg), cfg)
    by_name = {p.material.name: p for p in mesh.primitives if p.positions.shape[0]}
    bark = by_name["bark"]
    leaf = by_name.get("leaf")

    # Every primitive carries the full wind + tangent contract.
    for p in by_name.values():
        v = p.positions.shape[0]
        assert p.wind.shape == (v, 3)
        assert p.pivot.shape == (v, 3)
        assert p.wind_tier.shape == (v,)
        assert p.tangents.shape == (v, 4)
        assert np.all((p.wind[:, 0] >= 0.0) & (p.wind[:, 0] < 1.0))   # phase in [0,1)
        assert np.all((p.wind[:, 1] >= 0.0) & (p.wind[:, 1] <= 1.0))  # stiffness in [0,1]
        assert set(np.unique(p.wind[:, 2]).tolist()) <= {0.0, 1.0}     # leafMask binary
        assert np.all((p.wind_tier >= 0.0) & (p.wind_tier <= WIND_TIER_MAX))
        assert np.all(np.abs(p.tangents[:, 3]) == 1.0)                 # handedness ±1

    # Bark is wood (leafMask 0) and spans more than one tier (trunk + branches).
    assert np.all(bark.wind[:, 2] == 0.0)
    assert len(np.unique(bark.wind_tier)) >= 2
    # Stiffness hierarchy: the bark carries a real range (thick wood -> ~1, twigs -> ~0).
    assert bark.wind[:, 1].max() > bark.wind[:, 1].min()

    if leaf is not None:
        assert np.all(leaf.wind[:, 2] == 1.0)            # leaves are leafMask 1
        # Leaf tier = its branch's axis order (0..2), not a hardcoded 2 — so a
        # trunk-apex leaf stays tier 0 while branch leaves ride a tier-1+ swing.
        assert set(np.unique(leaf.wind_tier).tolist()) <= {0.0, 1.0, 2.0}
        assert leaf.wind_tier.max() >= 1.0               # most leaves hang on branches
        # Pivot is the branch base, not the leaf seat -> a real tier-1 moment arm.
        arm = np.linalg.norm(leaf.positions - leaf.pivot, axis=1)
        assert float(np.median(arm)) > 0.05


def test_thickest_bark_is_stiffest_near_collar():
    cfg = _cfg()
    mesh = build_mesh(simulate(cfg), cfg)
    bark = next(p for p in mesh.primitives if p.material.name == "bark")
    # Stiffness tracks diameter, which is largest at the (low) collar and tapers to
    # the (high) twigs — so stiffness and height are negatively correlated.
    stiff = bark.wind[:, 1].astype(np.float64)
    y = bark.positions[:, 1].astype(np.float64)
    assert np.corrcoef(stiff, y)[0, 1] < -0.1


def _cfg() -> Config:
    return Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=400),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, shoot_extension_max=0.1,
                      vigor_dormancy=0.5, max_simulation_years=8.0),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False), geom=GeomConfig(),
        seed=7, output=Path("x.glb"),
    )
