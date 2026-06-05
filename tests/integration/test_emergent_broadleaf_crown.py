"""The emergent broadleaf rounded crown (#97): under exposure: shadow_propagation
with neutral (non-cone) bounds, a *multiplicative* age hump on the light-driven
length grows a recognisably rounded / decurrent crown — widest in the mid-to-upper
crown, NOT the #94 cone (widest at the base) and NOT the raw shadow-prop inverted
feather-duster.

The rounding lever is the `pyramid` exposure measure (downward self-shadow, no side
light): it suppresses the lower-INTERIOR so the bole clears, where `skyview` keeps
the lower edge lit → a base-wide cone. `length_banking.profile = rounded` then
MULTIPLIES (not replaces) the light-driven length by a unimodal age hump — narrowing
the young apex and the oldest basal laterals, leaving the crown widest in the middle.

Heavy: the rounded form needs light-driven length (so self-shadowing clears the
base), which keeps a large bud pool. Bounded only via shade mortality + an
establish_threshold near each species' banked-vigor q95 (the prolific decussate
maple/ash carry ~25× oak's bud count, so they need a far higher threshold and a
shorter horizon — the pool re-explodes super-linearly past ~y14). Run at the
per-species bounded horizon with an internode guard; the full multi-seed numbers and
the y30 tractability limit are documented in docs/botany/realism-assessment.md.
"""
from __future__ import annotations

import pytest

from palubicki.config import load_config
from palubicki.sim.diagnostics import compute_metrics
from palubicki.sim.simulator import simulate

# Neutral (non-cone) bounds + pyramid self-shadow + rounded multiplicative hump.
_SHADOW = {
    "exposure": "shadow_propagation",
    "shadow.enabled": True,
    "shadow.measure": "pyramid",          # downward self-shadow → clears the base
    "shadow.mortality_enabled": True,     # bounds the pool + clears the lower interior
    "shadow.q_dormancy": 0.45,
    "sim.shade_mortality.light_threshold": 0.55,
    "sim.length_banking.enabled": True,
    "sim.length_banking.profile": "rounded",
    "sim.length_banking.release_years": 6.0,
    "sim.length_banking.decline_years": 12.0,
    "sim.length_banking.young_length_floor": 0.65,
    "sim.length_banking.old_length_floor": 0.40,
    "sim.length_banking.persist_rate_fraction": 0.50,  # establishment-engage gate only
    "geom.pipe_exponent": 4.0,            # the heavy pool thickens the bole
}

# Per-species envelope (generous, non-cone), establish_threshold ≈ banked-vigor q95
# (prolific maple/ash need ~40-45; oak's sparse crown bounds at ~2), horizon, and the
# internode guard. Birch is the monopodial weeping outlier: a gentler recipe (it makes
# little wood, so a lower threshold + its own slender pipe) and an upper-rounded oval.
_SPECIES = {
    "oak": dict(
        years=16, envelope=(5.5, 15.0, 5.5), establish=2.0,
        overrides={}, intern_max=80_000,
    ),
    "maple": dict(
        years=12, envelope=(5.0, 13.0, 5.0), establish=40.0,
        overrides={}, intern_max=200_000,
    ),
    "ash": dict(
        years=12, envelope=(4.5, 14.0, 4.5), establish=45.0,
        overrides={}, intern_max=250_000,
    ),
    "birch": dict(
        years=18, envelope=(5.0, 14.0, 5.0), establish=0.8,
        overrides={"geom.pipe_exponent": 2.3, "shadow.q_dormancy": 0.30,
                   "sim.shade_mortality.light_threshold": 0.40},
        intern_max=5_000,
    ),
}


def _sim(species: str, seed: int, tmp_path):
    spec = _SPECIES[species]
    rx, ry, rz = spec["envelope"]
    ov = {"seed": seed, "sim.max_simulation_years": spec["years"]}
    ov.update(_SHADOW)
    ov.update({
        "envelope.shape": "half_ellipsoid", "envelope.rx": rx,
        "envelope.ry": ry, "envelope.rz": rz,
        "sim.length_banking.establish_threshold": spec["establish"],
    })
    ov.update(spec["overrides"])
    cfg = load_config(yaml_path=None, cli_overrides=ov,
                      output=(tmp_path / "t.glb"), species=species)
    tree = simulate(cfg)
    return tree, compute_metrics(tree, cfg=cfg)


def _assert_rounded(m, *, inverted_ok: bool):
    """The crown is rounded — NOT the #94 cone and NOT a sharp spire.

    A cone is widest at the base (crown_widest_frac ~0.05), tapers to a point
    (apex_sharpness ~0.04) and narrows monotonically upward (crown_monotonicity
    ~-0.95). A rounded/decurrent crown is widest in the mid-to-upper crown with a
    filled (non-pointed) apex. `inverted_ok` allows the upper-rounded weeping form
    (birch), whose widest band sits high (crown_monotonicity > 0)."""
    assert m["crown_widest_frac"] >= 0.30          # widest mid/upper, not base (cone)
    assert m["apex_sharpness"] >= 0.10             # filled apex, not a spire tip
    assert m["crown_monotonicity"] > -0.85         # not the strong #94 cone taper
    if not inverted_ok:
        # Decurrent dome: widest band not pinned to the very top (feather-duster).
        assert m["crown_widest_frac"] <= 0.75


@pytest.mark.slow
@pytest.mark.parametrize("species", ["oak", "maple", "ash"])
def test_broadleaf_grows_a_rounded_decurrent_crown(species, tmp_path):
    """oak / maple / ash under pyramid shadow-prop + the rounded multiplicative hump
    grow a rounded/spreading crown (widest mid-crown), with the pool bounded."""
    tree, m = _sim(species, seed=0, tmp_path=tmp_path)
    _assert_rounded(m, inverted_ok=False)
    # The pool stayed bounded — the mortality + establish_threshold guard is working.
    assert len(tree.all_internodes) < _SPECIES[species]["intern_max"]


@pytest.mark.slow
def test_birch_grows_a_narrow_upper_rounded_crown(tmp_path):
    """Birch is the monopodial weeping outlier: a narrow, upper-rounded oval (widest
    high, fuller top) — still NOT a cone and NOT a sharp spire."""
    tree, m = _sim("birch", seed=0, tmp_path=tmp_path)
    _assert_rounded(m, inverted_ok=True)
    assert len(tree.all_internodes) < _SPECIES["birch"]["intern_max"]


@pytest.mark.slow
def test_rounded_is_not_the_cone_skyview_makes(tmp_path):
    """Contrast: the SAME species/bounds on the skyview measure with the cone profile
    (acropetal_ramp) makes a base-wide cone; the pyramid + rounded hump does not. The
    crown_widest_frac / crown_monotonicity separation is the #97 claim, in one run."""
    _, rounded = _sim("oak", seed=0, tmp_path=tmp_path)
    # The cone path: skyview + age-REPLACES-length monotone ramp (#94).
    ov = {"seed": 0, "sim.max_simulation_years": 16}
    ov.update(_SHADOW)
    ov.update({
        "shadow.measure": "skyview",
        "sim.length_banking.profile": "acropetal_ramp",
        "sim.length_banking.persist_rate_fraction": 0.45,
        "sim.length_banking.establish_threshold": 2.0,
        "envelope.shape": "half_ellipsoid", "envelope.rx": 5.5,
        "envelope.ry": 15.0, "envelope.rz": 5.5,
    })
    cfg = load_config(yaml_path=None, cli_overrides=ov,
                      output=(tmp_path / "c.glb"), species="oak")
    cone = compute_metrics(simulate(cfg), cfg=cfg)

    # The cone is widest at the base and narrows hard upward; the rounded crown is
    # widest higher and far less monotone.
    assert cone["crown_widest_frac"] < rounded["crown_widest_frac"]
    assert cone["crown_monotonicity"] < rounded["crown_monotonicity"]
    assert cone["apex_sharpness"] < rounded["apex_sharpness"] + 0.05
