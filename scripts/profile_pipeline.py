"""Profile the FULL generate pipeline: simulate -> build_mesh -> write_glb.

Times each phase separately, then cProfiles the geometry + export phases (the
non-sim part) so a perf pass can target mesh-build / glTF-export hot spots.

Usage:
    .venv/bin/python scripts/profile_pipeline.py SPECIES YEARS [SEED]
"""
from __future__ import annotations

import cProfile
import io
import pstats
import sys
import time
from pathlib import Path

from palubicki.config import load_config
from palubicki.export.gltf import write_glb_to_bytes
from palubicki.geom.builder import build_mesh
from palubicki.sim.simulator import simulate


def _config_to_dict(cfg):
    from palubicki.cli import _config_to_dict as c2d
    return c2d(cfg)


def main() -> int:
    species = sys.argv[1] if len(sys.argv) > 1 else "oak_emergent"
    years = float(sys.argv[2]) if len(sys.argv) > 2 else 14.0
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    cfg = load_config(
        yaml_path=None,
        cli_overrides={"sim.max_simulation_years": years, "seed": seed},
        output=Path("/tmp/profile_pipeline.glb"),
        species=species,
    )
    print(f"=== pipeline species={species} years={years} seed={seed} "
          f"exposure={cfg.exposure} ===", flush=True)

    t0 = time.perf_counter()
    tree = simulate(cfg)
    t_sim = time.perf_counter() - t0

    asset_meta = {"seed": cfg.seed, "config": _config_to_dict(cfg)}

    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()
    mesh = build_mesh(tree, cfg)
    t_mesh = time.perf_counter() - t0

    t0 = time.perf_counter()
    data = write_glb_to_bytes(mesh, asset_meta=asset_meta)
    t_export = time.perf_counter() - t0
    pr.disable()

    n_iod = len(tree.all_internodes)
    n_vert = sum(p.positions.shape[0] for p in mesh.primitives)
    n_tri = sum(p.indices.shape[0] // 3 for p in mesh.primitives)
    print(f"\nPHASE_TIMES sim={t_sim:.3f}s  mesh={t_mesh:.3f}s  export={t_export:.3f}s  "
          f"glb_MB={len(data)/1e6:.1f}", flush=True)
    print(f"SIZES internodes={n_iod}  vertices={n_vert}  triangles={n_tri}  "
          f"primitives={len(mesh.primitives)}", flush=True)

    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(28)
    print("\n===== MESH+EXPORT TOP 28 BY TOTTIME =====")
    print(s.getvalue())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
