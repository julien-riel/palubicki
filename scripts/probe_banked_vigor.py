"""Print the banked_vigor distribution of lateral axes under the rounded
shadow-prop recipe, so establish_threshold can be set analytically (≈ q90) per
species rather than by expensive trial-and-error (#97). Run at a short horizon."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from palubicki.config import load_config
from palubicki.sim.simulator import simulate
from palubicki.sim.tree import BudState

sys.path.insert(0, str(Path(__file__).parent))
from sweep_broadleaf_crown import SHADOW, CAL, _COMMON_SHADOW  # noqa: E402


def main():
    species = sys.argv[1]
    years = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    ov = {"seed": 0, "sim.max_simulation_years": years}
    ov.update(_COMMON_SHADOW)
    ov.update(SHADOW[species])
    ov["sim.length_banking.enabled"] = True
    ov["sim.length_banking.profile"] = "rounded"
    ov.update(CAL[species])
    # Disable mortality so we see the FULL banked distribution (what est must gate).
    ov["shadow.mortality_enabled"] = False
    ov["sim.length_banking.establish_threshold"] = 999.0  # nothing established
    cfg = load_config(yaml_path=None, cli_overrides=ov, output=Path("/tmp/bv.glb"), species=species)
    tree = simulate(cfg)
    bv = [float(b.banked_vigor) for b in tree.active_buds
          if b.axis_order >= 1 and b.state != BudState.DEAD]
    a = np.asarray(bv)
    print(f"{species} y{years}: n_lat_buds={a.size} internodes={len(tree.all_internodes)}")
    if a.size:
        for p in (50, 75, 90, 95, 99):
            print(f"  q{p}={np.percentile(a, p):.3f}", end="")
        print(f"  max={a.max():.3f}")


if __name__ == "__main__":
    main()
