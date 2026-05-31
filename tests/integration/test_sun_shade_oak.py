"""Phase 2C: end-to-end check that lower-canopy leaves are larger than upper."""
import numpy as np
import pytest

from palubicki.config import load_config
from palubicki.geom.leaves import selected_leaves
from palubicki.sim.simulator import simulate

pytestmark = pytest.mark.slow


def test_oak_lower_canopy_leaves_larger_than_upper(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="oak")
    tree = simulate(cfg)

    sites = selected_leaves(
        tree, foliage_depth=cfg.geom.foliage_depth,
        needle_cluster_spacing=cfg.geom.needle_cluster_spacing,
    )
    assert len(sites) > 10, f"too few foliage sites: {len(sites)}"

    # selected_leaves yields (leaf, stem_dir, source_internode, render_position).
    # Canopy height comes from the render position's y; shade from the source
    # internode's light_factor.
    ys = np.array([s[3][1] for s in sites])
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
    lf_upper = float(lfs[upper_mask].mean())
    lf_lower = float(lfs[lower_mask].mean())

    # Assert the MECHANISM, not a magnitude pinned to a particular tree shape.
    # The co-located-bud fix lets the leader survive, so the oak is taller with a
    # gentler top-to-bottom light gradient — the sun/shade effect is milder but
    # still correctly signed. An absolute "lower > 1.1x upper" bound was an
    # artifact of the pre-fix (shorter, more steeply shaded) canopy.
    #   (1) lower canopy is genuinely shadier than upper — the causal gradient,
    assert lf_lower < lf_upper - 0.02, (
        f"lower canopy should be shadier (drives the effect): "
        f"lf_lower={lf_lower:.3f}, lf_upper={lf_upper:.3f}"
    )
    #   (2) which makes lower-canopy leaves larger than upper.
    assert mean_lower > mean_upper, (
        f"expected lower > upper, got lower={mean_lower:.4f} upper={mean_upper:.4f}"
    )
