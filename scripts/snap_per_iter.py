"""Debug: dump a .glb + PNG snapshot after each iteration of the BHse loop.

Goal: trace WHEN the trunk apex starts bending away from vertical and what
the tree looks like one growth-season at a time.

Usage:
    .venv/bin/python scripts/snap_per_iter.py --species oak --seed 42 \
        --out-dir out/diag/iters_oak --iterations 35
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from palubicki.config import load_config
from palubicki.geom.builder import build_mesh
from palubicki.export.gltf import write_glb
from palubicki.render import Camera, render_mesh, save_png
from palubicki.render.io import _glb_to_mesh
from palubicki.sim.forest import build_forest
from palubicki.sim.light import LightGrid
from palubicki.sim.simulator import _iteration_step, _SimState


def _trunk_axis_drift(tree) -> tuple[float, float, float]:
    """Return (max_apex_y, mean_axis_deviation_deg, last_internode_pitch_deg)
    for the main axis (trunk: axis_order=0 chain)."""
    # Walk main axis: from root follow is_main_axis=True children.
    node = tree.root
    positions = [node.position.copy()]
    while True:
        nxt = None
        for iod in node.children_internodes:
            if iod.is_main_axis:
                nxt = iod.child_node
                break
        if nxt is None:
            break
        positions.append(nxt.position.copy())
        node = nxt
    if len(positions) < 2:
        return 0.0, 0.0, 0.0
    arr = np.asarray(positions)
    max_y = float(arr[:, 1].max())
    # Mean deviation: angle between each segment and +Y, averaged.
    segs = np.diff(arr, axis=0)
    seg_norms = np.linalg.norm(segs, axis=1)
    safe = seg_norms > 1e-9
    if not safe.any():
        return max_y, 0.0, 0.0
    seg_dirs = segs[safe] / seg_norms[safe, None]
    cos_to_up = np.clip(seg_dirs @ np.array([0.0, 1.0, 0.0]), -1.0, 1.0)
    dev_deg = float(np.degrees(np.arccos(cos_to_up)).mean())
    last_pitch = float(np.degrees(np.arccos(cos_to_up[-1])))
    return max_y, dev_deg, last_pitch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--species", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--iterations", type=int, default=None,
                    help="Override cfg.sim.max_iterations")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--no-sag", action="store_true",
                    help="Force sag.enabled=False before exporting each snapshot")
    ap.add_argument("--no-light", action="store_true",
                    help="Force light.enabled=False")
    ap.add_argument("--no-leaves", action="store_true",
                    help="Render PNG without leaves")
    ap.add_argument("--size", default="900x900")
    ap.add_argument("--elevation", type=float, default=5.0)
    ap.add_argument("--azimuth", type=float, default=30.0)
    args = ap.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    overrides: dict = {"seed": args.seed}
    if args.iterations is not None:
        overrides["sim.max_iterations"] = args.iterations
    if args.no_light:
        overrides["light.enabled"] = False
    if args.no_sag:
        overrides["sag.enabled"] = False
    cfg = load_config(
        yaml_path=Path(args.config) if args.config else None,
        cli_overrides=overrides,
        output=out_dir / "final.glb",
        species=args.species,
    )

    forest = build_forest(cfg)
    if cfg.light.enabled:
        forest.light_grid = LightGrid.from_config(cfg.light, cfg.envelope)

    state = _SimState()
    t0 = time.time()
    w, h = (int(x) for x in args.size.lower().split("x"))

    print(f"# iter  nodes  apex_y  mean_dev_deg  last_pitch_deg")
    for i in range(cfg.sim.max_iterations):
        if not any(t.active_buds for t in forest.trees):
            print(f"  break at iter {i}: no active buds")
            break
        nodes_created = _iteration_step(forest, cfg, i, state, t0)

        tree = forest.trees[0]
        apex_y, dev, last = _trunk_axis_drift(tree)
        print(f"  {i+1:3d}  {nodes_created:4d}  {apex_y:6.2f}  {dev:7.2f}  {last:8.2f}")

        # Snapshot: build mesh + render
        glb_path = out_dir / f"iter_{i+1:02d}.glb"
        png_path = out_dir / f"iter_{i+1:02d}.png"
        mesh = build_mesh(tree, cfg)
        write_glb(mesh, glb_path, asset_meta={
            "iteration": i + 1,
            "nodes_created": nodes_created,
            "apex_y": apex_y,
            "mean_axis_dev_deg": dev,
        })
        rmesh = _glb_to_mesh(glb_path, drop_leaves=args.no_leaves)
        cam = Camera.fit(rmesh, elevation_deg=args.elevation, azimuth_deg=args.azimuth)
        img = render_mesh(rmesh, size=(w, h), camera=cam, bg=(1.0, 1.0, 1.0, 1.0))
        save_png(img, png_path)


if __name__ == "__main__":
    main()
