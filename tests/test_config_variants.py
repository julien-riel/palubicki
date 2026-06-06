"""Opt-in emergent-form variants (#97): packaged `configs/variants/{species}_emergent.yaml`
overlays that flip a species onto `exposure: shadow_propagation` so its crown form
emerges from light competition, WITHOUT touching the shipped (bhse) preset.

These are fast wiring tests (no simulation). That the forms actually emerge is
covered by tests/integration/test_emergent_broadleaf_crown.py (rounded) and
test_emergent_cone.py (cone)."""
from __future__ import annotations

from pathlib import Path

import pytest

from palubicki.config import ConfigError, _list_variants, load_config

SPECIES = ("fir", "pine", "oak", "maple", "ash", "birch")


def _load(species, variant="emergent", overrides=None):
    return load_config(
        yaml_path=None, cli_overrides=overrides or {}, output=Path("x.glb"),
        species=species, variant=variant,
    )


def test_emergent_variant_exists_for_every_species():
    assert "emergent" in _list_variants()
    for sp in SPECIES:
        cfg = _load(sp)
        assert cfg.exposure == "shadow_propagation"
        assert cfg.shadow.enabled is True
        assert cfg.sim.length_banking.enabled is True
        # All emergent variants ship calibrated at a young (fast, bounded) horizon.
        assert cfg.sim.max_simulation_years == 10


def test_conifers_use_skyview_cone_broadleaves_use_pyramid_rounded():
    for sp in ("fir", "pine"):
        cfg = _load(sp)
        assert cfg.shadow.measure == "skyview"
        assert cfg.sim.length_banking.profile == "acropetal_ramp"   # the cone
    for sp in ("oak", "maple", "ash", "birch"):
        cfg = _load(sp)
        assert cfg.shadow.measure == "pyramid"
        assert cfg.sim.length_banking.profile == "rounded"          # the dome


def test_variant_overlays_not_the_shipped_preset():
    """The variant flips exposure; the bare preset stays on the default bhse."""
    base = load_config(yaml_path=None, cli_overrides={}, output=Path("x.glb"), species="oak")
    assert base.exposure == "bhse"
    emergent = _load("oak")
    assert emergent.exposure == "shadow_propagation"


def test_cli_overrides_still_beat_the_variant():
    """Merge order is species -> variant -> cli_overrides, so an explicit override wins."""
    cfg = _load("oak", overrides={"exposure": "bhse", "sim.max_simulation_years": 30})
    assert cfg.exposure == "bhse"
    assert cfg.sim.max_simulation_years == 30


def test_variant_without_species_raises():
    with pytest.raises(ConfigError, match="requires --species"):
        load_config(yaml_path=None, cli_overrides={}, output=Path("x.glb"), variant="emergent")


def test_unknown_variant_raises():
    with pytest.raises(ConfigError, match="no 'bogus' variant"):
        _load("oak", variant="bogus")
