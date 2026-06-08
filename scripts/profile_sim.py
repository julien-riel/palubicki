"""Profile the simulation hot path (simulate_forest only — no mesh/export).

Usage:
    .venv/bin/python scripts/profile_sim.py SPECIES YEARS [SEED]

Dumps cumulative + tottime cProfile stats and wall-clock for the sim loop, so a
performance pass can target the real hot spots under shadow-propagation.
"""
from __future__ import annotations

import cProfile
import io
import pstats
import sys
import time
from pathlib import Path

from palubicki.config import load_config
from palubicki.sim.simulator import simulate_forest


def main() -> int:
    species = sys.argv[1] if len(sys.argv) > 1 else "oak_emergent"
    years = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    overrides = {"sim.max_simulation_years": years, "seed": seed}
    cfg = load_config(
        yaml_path=None, cli_overrides=overrides,
        output=Path("/tmp/profile_sim.glb"), species=species,
    )

    print(f"=== profile_sim species={species} years={years} seed={seed} ===", flush=True)
    print(f"exposure={cfg.exposure} measure={getattr(cfg.shadow, 'measure', None)} "
          f"num_iterations={cfg.sim.num_iterations}", flush=True)

    # Warm import paths so first-call import cost is out of the timed region.
    pr = cProfile.Profile()
    t0 = time.perf_counter()
    pr.enable()
    forest = simulate_forest(cfg)
    pr.disable()
    wall = time.perf_counter() - t0

    n_internodes = sum(len(t.all_internodes) for t in forest.trees)
    n_buds = sum(len(t.active_buds) for t in forest.trees)
    print(f"\nWALL_CLOCK_SECONDS={wall:.3f}  internodes={n_internodes}  active_buds={n_buds}", flush=True)

    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats("tottime")
    ps.print_stats(30)
    print("\n===== TOP 30 BY TOTTIME =====")
    print(s.getvalue())

    s2 = io.StringIO()
    ps2 = pstats.Stats(pr, stream=s2).sort_stats("cumulative")
    ps2.print_stats(30)
    print("\n===== TOP 30 BY CUMULATIVE =====")
    print(s2.getvalue())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
