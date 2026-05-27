# tests/integration/test_reiteration_after_shed.py
from unittest.mock import patch

import pytest

from palubicki.cli import main


pytestmark = pytest.mark.slow


def test_reiteration_produces_activations(tmp_path):
    """With reserves > 0 and reactivation > 0, shed-driven activations occur.
    With reserves == 0, activations must be zero even if many sheds happen."""
    from palubicki.config import load_config
    from palubicki.sim.simulator import simulate
    import palubicki.sim.shedding as shedding_mod

    counter = {"calls": 0, "activations": 0}
    real = shedding_mod.activate_reserves_on_shed

    def spy(parent_node, n_to_activate=1):
        counter["calls"] += 1
        out = real(parent_node, n_to_activate=n_to_activate)
        counter["activations"] += len(out)
        return out

    # Run 1: oak preset (reserves=2, reactivation=1) — expect activations.
    with patch.object(shedding_mod, "activate_reserves_on_shed", side_effect=spy):
        cfg = load_config(
            yaml_path=None,
            cli_overrides={"sim.max_iterations": 25, "envelope.marker_count": 3000},
            output=tmp_path / "oak.glb", species="oak",
        )
        simulate(cfg)
    oak_activations = counter["activations"]

    counter["calls"] = 0
    counter["activations"] = 0

    # Run 2: oak preset but force reserves to 0 — expect zero activations.
    with patch.object(shedding_mod, "activate_reserves_on_shed", side_effect=spy):
        cfg = load_config(
            yaml_path=None,
            cli_overrides={
                "sim.max_iterations": 25,
                "envelope.marker_count": 3000,
                "phyllotaxy.dormant_reserve_count": 0,
            },
            output=tmp_path / "oak0.glb", species="oak",
        )
        simulate(cfg)
    no_reserve_activations = counter["activations"]

    assert oak_activations > 0, "expected oak preset to produce shed-driven activations"
    assert no_reserve_activations == 0, (
        f"expected 0 activations with dormant_reserve_count=0, got {no_reserve_activations}"
    )
