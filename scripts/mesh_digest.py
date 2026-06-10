"""Deterministic digest of build_mesh output — verifies a geometry-build perf
optimization leaves the rendered mesh (and thus the .glb) BIT-IDENTICAL.

Hashes every primitive's raw vertex/index/attribute bytes.

Usage:
    .venv/bin/python scripts/mesh_digest.py SPECIES YEARS [SEED]
Prints: MESHDIGEST <hex>  prims=<n> verts=<n> tris=<n>
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np

from palubicki.config import load_config
from palubicki.geom.builder import build_mesh
from palubicki.sim.simulator import simulate


def _h(h, arr):
    if arr is None:
        h.update(b"None")
    else:
        h.update(np.ascontiguousarray(arr).tobytes())


def main() -> int:
    species = sys.argv[1] if len(sys.argv) > 1 else "oak_emergent"
    years = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    cfg = load_config(
        yaml_path=None,
        cli_overrides={"sim.max_simulation_years": years, "seed": seed},
        output=Path("/tmp/mesh_digest.glb"),
        species=species,
    )
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    h = hashlib.sha256()
    n_v = n_t = 0
    for p in mesh.primitives:
        for attr in ("positions", "normals", "uvs", "indices",
                     "tangents", "tint", "wind", "pivot", "wind_tier"):
            _h(h, getattr(p, attr, None))
        n_v += p.positions.shape[0]
        n_t += p.indices.shape[0] // 3
    print(f"MESHDIGEST {h.hexdigest()}  prims={len(mesh.primitives)} verts={n_v} tris={n_t}  "
          f"species={species} years={years} seed={seed}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
