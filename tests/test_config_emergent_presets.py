"""Standalone `*_emergent` species presets (#97): full presets that grow each
species' form from light competition under `exposure: shadow_propagation`, instead
of the prescribed `envelope.shape`. The base presets (oak, fir, ...) stay on `bhse`.

Fast wiring tests (no simulation). That the forms actually emerge is covered by
tests/integration/test_emergent_broadleaf_crown.py (rounded) and
test_emergent_cone.py (cone)."""
from __future__ import annotations

from pathlib import Path

from palubicki.config import _list_species, load_config

# species -> (shadow measure, length_banking profile, max_simulation_years).
EMERGENT = {
    "fir_emergent": ("skyview", "acropetal_ramp", 30),
    "pine_emergent": ("skyview", "acropetal_ramp", 30),
    "oak_emergent": ("pyramid", "rounded", 18),
    "birch_emergent": ("pyramid", "rounded", 18),
    "maple_emergent": ("pyramid", "rounded", 12),
    "ash_emergent": ("pyramid", "rounded", 12),
}


def _load(species):
    return load_config(yaml_path=None, cli_overrides={}, output=Path("x.glb"), species=species)


def test_every_species_has_an_emergent_preset():
    available = set(_list_species())
    for sp in EMERGENT:
        assert sp in available, f"{sp} not packaged"


def test_emergent_presets_use_shadow_propagation_with_expected_form():
    for sp, (measure, profile, years) in EMERGENT.items():
        cfg = _load(sp)
        assert cfg.exposure == "shadow_propagation", sp
        assert cfg.shadow.enabled is True, sp
        assert cfg.shadow.measure == measure, sp
        assert cfg.sim.length_banking.enabled is True, sp
        assert cfg.sim.length_banking.profile == profile, sp
        # Calibrated at the largest tractable horizon for the species.
        assert cfg.sim.max_simulation_years == years, sp


def test_base_presets_stay_bhse():
    """The emergent presets are SEPARATE files; the base presets are untouched."""
    for base in ("oak", "fir", "pine", "maple", "ash", "birch"):
        assert _load(base).exposure == "bhse", base


def test_decussate_broadleaves_carry_a_high_establish_threshold():
    """maple/ash (~25x oak's bud count) need a far higher establish_threshold than
    oak to bound the pool (the #97 pool-bounding lever)."""
    oak = _load("oak_emergent").sim.length_banking.establish_threshold
    for sp in ("maple_emergent", "ash_emergent"):
        assert _load(sp).sim.length_banking.establish_threshold > oak * 10
