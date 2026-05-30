# src/palubicki/cli.py
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import fields, is_dataclass
from pathlib import Path

import yaml

from palubicki.config import (
    Config,
    ConfigError,
    EnvelopeConfig,
    GeomConfig,
    PhyllotaxyConfig,
    SheddingConfig,
    SimConfig,
    TropismConfig,
    _list_species,
    _load_packaged_species,
    load_config,
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
    if args.command == "preview":
        return _cmd_preview(args)
    if args.command == "edit":
        return _cmd_edit(args)
    if args.command == "diagnose":
        return _cmd_diagnose(args)

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
    g.add_argument("--years", type=float, default=None, dest="years")
    g.add_argument("--dt-years", type=float, default=None, dest="dt_years")
    g.add_argument("--lambda", dest="lambda_apical", type=float, default=None)
    g.add_argument("--leaf-texture", type=Path, default=None)
    g.add_argument("--no-leaves", action="store_true")
    g.add_argument("--no-shed", action="store_true")
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

    dd = sub.add_parser("dump-defaults", help="Print full default config as YAML")
    dd.add_argument("--species", default=None,
                    help="Print the packaged preset for this species instead of generic defaults")

    dc = sub.add_parser("dump-config", help="Extract config embedded in a .glb")
    dc.add_argument("glb_path", type=Path)

    fst = sub.add_parser("forest", help="Generate a multi-tree forest with optional obstacles and write .glb")
    fst.add_argument("-o", "--output", type=Path, required=True)
    fst.add_argument("--config", type=Path, required=True)
    fst.add_argument("--seed", type=int, default=None, help="Override cfg.seed")
    fst.add_argument("--log-level", choices=["DEBUG", "INFO", "WARN", "WARNING", "ERROR"], default="INFO")
    fst.add_argument("--validate", action="store_true")
    fst.add_argument("--save-config", type=Path, default=None)

    pv = sub.add_parser("preview", help="Render a .glb to a diagnostic PNG")
    pv.add_argument("glb_path", type=Path)
    pv.add_argument("-o", "--output", type=Path, required=True)
    pv.add_argument("--size", type=_parse_size, default=(800, 800),
                    help="Target image size as WxH (default 800x800)")
    pv.add_argument("--elevation", type=float, default=20.0,
                    help="Camera elevation in degrees (default 20)")
    pv.add_argument("--azimuth", type=float, default=35.0,
                    help="Camera azimuth in degrees (default 35)")
    pv.add_argument("--distance", type=float, default=None,
                    help="Camera distance (default: auto-fit)")
    pv.add_argument("--bg", type=_parse_bg, default=(1.0, 1.0, 1.0, 1.0),
                    help="Background: white | black | transparent (default white)")
    pv.add_argument("--no-leaves", action="store_true",
                    help="Filter out green-dominant primitives (leaves)")

    ed = sub.add_parser("edit", help="Launch the browser-based parameter editor")
    ed.add_argument("--config", type=Path, default=None)
    ed.add_argument("--species",
                    choices=species_choices if species_choices else None,
                    default=None)
    ed.add_argument("--seed", type=int, default=None,
                    help="Initial seed (overrides --config / --species).")
    ed.add_argument("--port", type=int, default=8765)
    ed.add_argument("--no-browser", action="store_true")

    dg = sub.add_parser("diagnose", help="Compute and print structural metrics for a generated tree")
    dg.add_argument("--config", type=Path, default=None)
    dg.add_argument("--species",
                    choices=species_choices if species_choices else None,
                    default=None)
    dg.add_argument("--seed", type=_parse_seed_list, default=[0],
                    help="Seed N or comma-separated list N,M,...")
    dg.add_argument("--json", action="store_true",
                    help="Emit raw metrics dict as JSON (skips the report layout)")
    dg.add_argument("--log-level", choices=["DEBUG", "INFO", "WARN", "WARNING", "ERROR"],
                    default="WARNING")

    return parser


def _parse_size(value: str) -> tuple[int, int]:
    """Parse 'WxH' → (W, H). Raises argparse.ArgumentTypeError on garbage."""
    parts = value.lower().split("x")
    if len(parts) != 2 or not all(parts):
        raise argparse.ArgumentTypeError(f"invalid --size {value!r}: expected WxH")
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"invalid --size {value!r}: not integers") from err
    if w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError(f"--size must be positive, got {value!r}")
    return (w, h)


_BG_PRESETS = {
    "white": (1.0, 1.0, 1.0, 1.0),
    "black": (0.0, 0.0, 0.0, 1.0),
    "transparent": (1.0, 1.0, 1.0, 0.0),
}


def _parse_bg(value: str) -> tuple[float, float, float, float]:
    """Parse a --bg preset name → RGBA tuple."""
    try:
        return _BG_PRESETS[value]
    except KeyError as err:
        raise argparse.ArgumentTypeError(
            f"invalid --bg {value!r}: choose from {sorted(_BG_PRESETS)}"
        ) from err


def _parse_seed_list(value: str) -> list[int]:
    """Parse 'N' or 'N,M,...' → [int, ...]. Raises ArgumentTypeError on bad input."""
    parts = value.split(",")
    if not parts or any(p.strip() == "" for p in parts):
        raise argparse.ArgumentTypeError(f"invalid --seed {value!r}: empty entry")
    try:
        return [int(p) for p in parts]
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"invalid --seed {value!r}: not all integers") from err


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
    if args.years is not None:
        overrides["sim.max_simulation_years"] = args.years
    if args.dt_years is not None:
        overrides["sim.dt_years"] = args.dt_years
    if args.lambda_apical is not None:
        overrides["sim.lambda_apical"] = args.lambda_apical
    if args.leaf_texture is not None:
        overrides["geom.leaf_texture"] = args.leaf_texture
    if args.no_leaves:
        overrides["geom.enable_leaves"] = False
    if args.no_shed:
        overrides["shedding.enabled"] = False
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
            "simulation_years": cfg.sim.max_simulation_years,
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
        from palubicki.export.gltf import write_glb_forest
        from palubicki.sim.simulator import simulate_forest

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


def _cmd_preview(args) -> int:
    try:
        from palubicki.render import (
            Camera,
            RenderDependencyError,
            RenderError,
            render_mesh,
            save_png,
        )
        from palubicki.render.io import _glb_to_mesh
    except ImportError:
        print(
            "preview error: render extra not installed. "
            "Run: pip install -e '.[render]'",
            file=sys.stderr,
        )
        return 2

    try:
        mesh = _glb_to_mesh(args.glb_path, drop_leaves=args.no_leaves)
        cam_overrides = {
            "elevation_deg": args.elevation,
            "azimuth_deg": args.azimuth,
        }
        if args.distance is not None:
            cam_overrides["distance"] = args.distance
        cam = Camera.fit(mesh, **cam_overrides)
        img = render_mesh(mesh, size=args.size, camera=cam, bg=args.bg)
        save_png(img, args.output)
    except RenderDependencyError as e:
        # matplotlib missing at runtime (setup error) → exit 2
        print(f"preview error: {e}", file=sys.stderr)
        return 2
    except RenderError as e:
        # Bad data / runtime failure → exit 1
        print(f"preview error: {e}", file=sys.stderr)
        return 1
    return 0


def _cmd_dump_defaults(args) -> int:
    if args.species is not None:
        try:
            data = _load_packaged_species(args.species)
        except ConfigError as e:
            print(f"config error: {e}", file=sys.stderr)
            return 2
        yaml.safe_dump(data, sys.stdout, sort_keys=False)
        return 0

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


def _cmd_edit(args) -> int:
    try:
        import uvicorn

        from palubicki.edit.server import create_app
    except ImportError:
        print(
            "edit error: extra not installed. Run: pip install -e '.[edit]'",
            file=sys.stderr,
        )
        return 2

    overrides: dict = {}
    if args.seed is not None:
        overrides["seed"] = args.seed
    try:
        cfg = load_config(
            yaml_path=args.config,
            cli_overrides=overrides,
            output=Path("tree.glb"),
            species=args.species,
        )
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    port = _find_free_port(args.port)
    if port is None:
        print(
            f"no free port in range {args.port}..{args.port + 9}",
            file=sys.stderr,
        )
        return 1

    if not args.no_browser:
        _schedule_open_browser(port)

    app = create_app(cfg)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    return 0


def _find_free_port(start: int) -> int | None:
    import socket
    for p in range(start, start + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return None


def _schedule_open_browser(port: int) -> None:
    import threading
    import time
    import webbrowser

    def _open():
        time.sleep(0.5)
        webbrowser.open(f"http://127.0.0.1:{port}/")

    threading.Thread(target=_open, daemon=True).start()


def _cmd_diagnose(args) -> int:
    import json

    level_name = "WARNING" if args.log_level == "WARN" else args.log_level
    logging.basicConfig(
        level=getattr(logging, level_name),
        format="%(message)s",
    )

    from palubicki.sim.diagnostics import compute_metrics, format_report

    seeds: list[int] = args.seed if isinstance(args.seed, list) else [args.seed]

    trees = []
    cfg = None
    for s in seeds:
        try:
            cfg = load_config(
                yaml_path=args.config,
                cli_overrides={"seed": s},
                output=Path("tree.glb"),
                species=args.species,
            )
        except ConfigError as e:
            print(f"config error: {e}", file=sys.stderr)
            return 2
        try:
            trees.append(simulate(cfg))
        except (ValueError, RuntimeError) as e:
            print(f"diagnose error: {type(e).__name__}: {e}", file=sys.stderr)
            return 1

    metrics = compute_metrics(trees if len(trees) > 1 else trees[0], cfg=cfg)

    if args.json:
        print(json.dumps(metrics, indent=2, default=str))
    else:
        print(format_report(metrics, seeds=seeds, species=args.species))
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
