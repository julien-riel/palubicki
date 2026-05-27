"""Phase 2C: end-to-end check that lower-canopy leaves are larger than upper."""
import numpy as np
import pytest

from palubicki.config import load_config
from palubicki.geom.leaves import _collect_foliage_sites
from palubicki.sim.simulator import simulate


pytestmark = pytest.mark.slow


def test_oak_lower_canopy_leaves_larger_than_upper(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="oak")
    tree = simulate(cfg)

    sites = _collect_foliage_sites(tree, cfg.geom.foliage_depth)
    assert len(sites) > 10, f"too few foliage sites: {len(sites)}"

    ys = np.array([s[0][1] for s in sites])
    lfs = np.array([
        s[2].light_factor if s[2] is not None else 1.0 for s in sites
    ])
    leaf_size = cfg.geom.leaf_size
    k = cfg.geom.leaf_sun_shade_k
    eff_sizes = np.clip(
        leaf_size * (1.0 + k * (1.0 - lfs)),
        0.5 * leaf_size, 2.0 * leaf_size,
    )

    y_max = ys.max()
    y_min = ys.min()
    span = max(1e-6, y_max - y_min)
    upper_mask = ys > y_min + 0.7 * span
    lower_mask = ys < y_min + 0.3 * span

    if not upper_mask.any() or not lower_mask.any():
        pytest.skip("oak canopy did not develop vertical spread in this run")

    mean_upper = float(eff_sizes[upper_mask].mean())
    mean_lower = float(eff_sizes[lower_mask].mean())
    assert mean_lower > 1.1 * mean_upper, (
        f"expected lower > 1.1x upper, got lower={mean_lower:.4f} upper={mean_upper:.4f}"
    )
