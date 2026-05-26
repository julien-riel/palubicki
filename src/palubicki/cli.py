# src/palubicki/cli.py
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path

import yaml

from palubicki.config import (
    Config, ConfigError, EnvelopeConfig, GeomConfig, LightConfig, PhyllotaxyConfig,
    SheddingConfig, SimConfig, TropismConfig, _list_species, load_config,
)
from palubicki.export.gltf import ExportError, write_glb
from palubicki.geom.builder import build_mesh
from palubicki.sim.simulator import simulate


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate":
        return _cmd_generate(args)
    if args.command == "dump-defaults":
        return _cmd_dump_defaults(args)
    if args.command == "dump-config":
        return _cmd_dump_config(args)
    if args.command == "forest":
        return _cmd_forest(args)

    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="palubicki")
    sub = parser.add_subparsers(dest="command")

    g = sub.add_parser("generate", help="Generate a tree and write .glb")
    g.add_argument("-o", "--output", type=Path, required=True)
    g.add_argument("--config", type=Path, default=None)
    g.add_argument("--seed", type=int, default=None)
    g.add_argument("--envelope", choices=["sphere", "ellipsoid", "cone", "half_ellipsoid"], default=None)
    g.add_argument("--envelope-radii", nargs=3, type=float, metavar=("RX", "RY", "RZ"), default=None)
    g.add_argument("--marker-count", type=int, default=None)
    g.add_argument("--iterations", type=int, default=None)
    g.add_argument("--lambda", dest="lambda_apical", type=float, default=None)
    g.add_argument("--w-gravity", type=float, default=None)
    g.add_argument("--leaf-texture", type=Path, default=None)
    g.add_argument("--no-leaves", action="store_true")
    g.add_argument("--no-shed", action="store_true")
    g.add_argument("--no-resample", action="store_true",
                   help="disable re-perception per substep (debug / legacy behavior)")
    g.add_argument("--ring-sides", type=int, default=None)
    g.add_argument("--log-level", choices=["DEBUG", "INFO", "WARN", "WARNING", "ERROR"], default="INFO")
    g.add_argument("--validate", action="store_true")
    g.add_argument("--save-config", type=Path, default=None)
    g.add_argument("--light-enabled", action="store_true",
                   help="Enable V2 voxel light shadowing (BHls hybrid)")
    g.add_argument("--light-k", type=float, default=None,
                   help="Beer-Lambert absorption coefficient (default 0.5)")
    g.add_argument("--light-rays", type=int, default=None,
                   help="Hemispheric rays per bud (default 16)")
    g.add_argument("--light-res", type=int, default=None,
                   help="Light grid resolution N → N×N×N cells (default 64)")

    species_choices = _list_species()
    g.add_argument("--species",
                   choices=species_choices if species_choices else None,
                   default=None,
                   help=f"Load a packaged species preset (choices: {', '.join(species_choices) if species_choices else 'none'})")

    sub.add_parser("dump-defaults", help="Print full default config as YAML")

    dc = sub.add_parser("dump-config", help="Extract config embedded in a .glb")
    dc.add_argument("glb_path", type=Path)

    fst = sub.add_parser("forest", help="Generate a multi-tree forest with optional obstacles and write .glb")
    fst.add_argument("-o", "--output", type=Path, required=True)
    fst.add_argument("--config", type=Path, required=True)
    fst.add_argument("--seed", type=int, default=None, help="Override cfg.seed")
    fst.add_argument("--log-level", choices=["DEBUG", "INFO", "WARN", "WARNING", "ERROR"], default="INFO")
    fst.add_argument("--validate", action="store_true")
    fst.add_argument("--save-config", type=Path, default=None)

    return parser


def _cmd_generate(args) -> int:
    logging.basicConfig(level=getattr(logging, args.log_level.replace("WARN", "WARNING")),
                        format="%(message)s")

    overrides: dict = {}
    if args.seed is not None:
        overrides["seed"] = args.seed
    if args.envelope is not None:
        overrides["envelope.shape"] = args.envelope
    if args.envelope_radii is not None:
        overrides["envelope.rx"] = args.envelope_radii[0]
        overrides["envelope.ry"] = args.envelope_radii[1]
        overrides["envelope.rz"] = args.envelope_radii[2]
    if args.marker_count is not None:
        overrides["envelope.marker_count"] = args.marker_count
    if args.iterations is not None:
        overrides["sim.max_iterations"] = args.iterations
    if args.lambda_apical is not None:
        overrides["sim.lambda_apical"] = args.lambda_apical
    if args.w_gravity is not None:
        overrides["tropism.w_gravity"] = args.w_gravity
    if args.leaf_texture is not None:
        overrides["geom.leaf_texture"] = args.leaf_texture
    if args.no_leaves:
        overrides["geom.enable_leaves"] = False
    if args.no_shed:
        overrides["shedding.enabled"] = False
    if args.no_resample:
        overrides["sim.re_perceive_per_substep"] = False
    if args.ring_sides is not None:
        overrides["geom.ring_sides"] = args.ring_sides
    if args.light_enabled:
        overrides["light.enabled"] = True
    if args.light_k is not None:
        overrides["light.k_absorption"] = args.light_k
    if args.light_rays is not None:
        overrides["light.n_rays"] = args.light_rays
    if args.light_res is not None:
        overrides["light.grid_resolution"] = [args.light_res, args.light_res, args.light_res]

    try:
        cfg = load_config(
            yaml_path=args.config,
            cli_overrides=overrides,
            output=args.output,
            species=args.species,
        )
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    try:
        tree = simulate(cfg)
        mesh = build_mesh(tree, cfg)
        asset_meta = {
            "seed": cfg.seed,
            "envelope": cfg.envelope.shape,
            "iterations": cfg.sim.max_iterations,
            "config": _config_to_dict(cfg),
        }
        write_glb(mesh, cfg.output, asset_meta=asset_meta)
    except ExportError as e:
        print(f"export error: {e}", file=sys.stderr)
        return 1

    if args.save_config is not None:
        with open(args.save_config, "w") as f:
            yaml.safe_dump(_config_to_dict(cfg), f, sort_keys=False)

    if args.validate:
        import pygltflib
        loaded = pygltflib.GLTF2().load(str(cfg.output))
        n_prim = len(loaded.meshes[0].primitives) if loaded.meshes else 0
        print(f"validated: {n_prim} primitives", file=sys.stderr)

    return 0


def _cmd_forest(args) -> int:
    logging.basicConfig(level=getattr(logging, args.log_level.replace("WARN", "WARNING")),
                        format="%(message)s")

    overrides: dict = {}
    if args.seed is not None:
        overrides["seed"] = args.seed

    try:
        cfg = load_config(yaml_path=args.config, cli_overrides=overrides, output=args.output)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    try:
        from palubicki.sim.simulator import simulate_forest
        from palubicki.export.gltf import write_glb_forest

        forest = simulate_forest(cfg)
        asset_meta = {
            "seed": cfg.seed,
            "n_trees": len(forest.trees),
            "n_obstacles": len(forest.obstacles),
            "config": _config_to_dict(cfg),
        }
        write_glb_forest(forest, cfg, cfg.output, asset_meta=asset_meta)
    except ExportError as e:
        print(f"export error: {e}", file=sys.stderr)
        return 1
    except (ValueError, OSError, ImportError) as e:
        print(f"forest error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    if args.save_config is not None:
        with open(args.save_config, "w") as f:
            yaml.safe_dump(_config_to_dict(cfg), f, sort_keys=False)

    if args.validate:
        import pygltflib
        loaded = pygltflib.GLTF2().load(str(cfg.output))
        n_nodes = len(loaded.nodes)
        print(f"validated: {n_nodes} nodes", file=sys.stderr)

    return 0


def _cmd_dump_defaults(_args) -> int:
    default = Config(
        envelope=EnvelopeConfig(),
        sim=SimConfig(),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(),
        geom=GeomConfig(),
        output=Path("tree.glb"),
    )
    yaml.safe_dump(_config_to_dict(default), sys.stdout, sort_keys=False)
    return 0


def _cmd_dump_config(args) -> int:
    import pygltflib
    loaded = pygltflib.GLTF2().load(str(args.glb_path))
    extras = (loaded.asset.extras or {}) if loaded.asset else {}
    config = extras.get("config")
    if not config:
        print("no config found in asset.extras", file=sys.stderr)
        return 1
    yaml.safe_dump(config, sys.stdout, sort_keys=False)
    return 0


def _config_to_dict(cfg: Config) -> dict:
    out: dict = {}
    for f in fields(cfg):
        v = getattr(cfg, f.name)
        if is_dataclass(v):
            out[f.name] = {fi.name: _scalar(getattr(v, fi.name)) for fi in fields(v)}
        else:
            out[f.name] = _scalar(v)
    return out


def _scalar(v):
    if isinstance(v, Path):
        return str(v)
    if isinstance(v, tuple):
        return [_scalar(x) if not isinstance(x, (int, float, str)) else x for x in v]
    if is_dataclass(v):
        return {f.name: _scalar(getattr(v, f.name)) for f in fields(v)}
    if isinstance(v, dict):
        return {k: _scalar(val) for k, val in v.items()}
    return v


if __name__ == "__main__":
    sys.exit(main())
