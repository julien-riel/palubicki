"""Deterministic digest of a finished simulation — for verifying that a
performance optimization leaves the emergent form BIT-IDENTICAL.

Hashes every internode's geometry + physiological state and every active bud's
position/direction/vigor, so any change in the simulated tree (positions,
diameters, lengths, vigor, banking, sag offsets) flips the digest.

Usage:
    .venv/bin/python scripts/sim_digest.py SPECIES YEARS [SEED]
Prints a single line:  DIGEST <hex>  internodes=<n>  buds=<n>
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np

from palubicki.config import load_config
from palubicki.sim.simulator import simulate_forest


def _round(arr: np.ndarray) -> bytes:
    # Hash raw float64 bytes — we want EXACT (bit) identity, no tolerance.
    return np.ascontiguousarray(arr, dtype=np.float64).tobytes()


def digest(forest) -> tuple[str, int, int]:
    h = hashlib.sha256()
    n_iod = 0
    n_bud = 0
    for tree in forest.trees:
        # Stable order: all_internodes is append-order (deterministic).
        for iod in tree.all_internodes:
            n_iod += 1
            h.update(_round(iod.parent_node.position))
            h.update(_round(iod.child_node.position))
            h.update(_round(iod.parent_node.sag_offset))
            h.update(_round(iod.child_node.sag_offset))
            h.update(_round(np.array([
                iod.length, iod.length_target, iod.diameter,
                iod.vigor, iod.banked_vigor, iod.light_factor,
                iod.birth_time, iod.average_quality(),
            ])))
        for bud in tree.active_buds:
            n_bud += 1
            h.update(_round(bud.position))
            h.update(_round(bud.direction))
            h.update(_round(np.array([
                bud.recent_vigor, bud.banked_vigor, bud.axis_birth_time,
                float(bud.axis_order), float(bud.state.value),
            ])))
    return h.hexdigest(), n_iod, n_bud


def main() -> int:
    species = sys.argv[1] if len(sys.argv) > 1 else "oak_emergent"
    years = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    cfg = load_config(
        yaml_path=None,
        cli_overrides={"sim.max_simulation_years": years, "seed": seed},
        output=Path("/tmp/sim_digest.glb"),
        species=species,
    )
    forest = simulate_forest(cfg)
    hexd, n_iod, n_bud = digest(forest)
    print(f"DIGEST {hexd}  internodes={n_iod}  buds={n_bud}  "
          f"species={species} years={years} seed={seed}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
