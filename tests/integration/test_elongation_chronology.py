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
            # 8000 markers (oak's real preset is 25000). The previous 2000 was a
            # fast proxy that only sustained growth because the pre-#24 phyllotaxy
            # bug scattered lateral buds across scrambled azimuths, accidentally
            # reaching sparse markers. With correct per-axis divergence (#24), 2000
            # is too sparse for this 5×6.5 oak envelope — the tree stalls by year 8
            # (10 internodes), leaving no late-born internodes to compare. 8000
            # restores a multi-year tree (~1100 internodes through year 29) so the
            # chronology assertion below actually exercises age-driven shortening.
            "envelope.marker_count": 8000,
            "sim.max_simulation_years": 30,
        },
        output=tmp_path / "oak.glb",
        species="oak",
    )
    tree = simulate(cfg)

    early = [iod.length_target for iod in tree.all_internodes if iod.birth_time < 10]
    late = [iod.length_target for iod in tree.all_internodes if iod.birth_time >= 20]
    assert len(early) > 5 and len(late) > 5, (
        f"insufficient samples: early={len(early)} late={len(late)}"
    )
    mean_early = statistics.fmean(early)
    mean_late = statistics.fmean(late)
    assert mean_late < mean_early * 0.8, (
        f"chronology not visible: mean_early={mean_early:.4f}, mean_late={mean_late:.4f}"
    )
