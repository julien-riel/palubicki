"""Verify the visible chronology: late-born internodes are shorter than early-born."""
import statistics

import pytest


@pytest.mark.slow
def test_oak_late_internodes_shorter_than_early(tmp_path):
    from palubicki.config import load_config
    from palubicki.sim.simulator import simulate

    cfg = load_config(
        yaml_path=None,
        cli_overrides={
            "envelope.marker_count": 2000,
            "sim.max_iterations": 30,
        },
        output=tmp_path / "oak.glb",
        species="oak",
    )
    tree = simulate(cfg)

    early = [iod.length_target for iod in tree.all_internodes if iod.birth_iteration < 10]
    late = [iod.length_target for iod in tree.all_internodes if iod.birth_iteration >= 20]
    assert len(early) > 5 and len(late) > 5, (
        f"insufficient samples: early={len(early)} late={len(late)}"
    )
    mean_early = statistics.fmean(early)
    mean_late = statistics.fmean(late)
    assert mean_late < mean_early * 0.8, (
        f"chronology not visible: mean_early={mean_early:.4f}, mean_late={mean_late:.4f}"
    )
