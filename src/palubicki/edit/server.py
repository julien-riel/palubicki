"""FastAPI app for the browser-based tree parameter editor."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from palubicki.config import Config, ConfigError, load_config
from palubicki.edit.config_io import config_dict_to_overrides, config_to_dict_for_ui
from palubicki.edit.schema import build_schema
from palubicki.export.gltf import ExportError, write_glb_to_bytes
from palubicki.geom.builder import build_mesh
from palubicki.sim.simulator import simulate

logger = logging.getLogger("palubicki.edit")


def create_app(initial_config: Config) -> FastAPI:
    app = FastAPI(title="palubicki edit", version="0.1.0")
    app.state.initial_config = initial_config

    @app.get("/api/schema")
    def get_schema() -> dict:
        return build_schema()

    @app.get("/api/initial")
    def get_initial() -> dict:
        return config_to_dict_for_ui(app.state.initial_config)

    @app.post("/api/species/{name}")
    def post_species(name: str) -> JSONResponse:
        try:
            cfg = load_config(
                yaml_path=None,
                cli_overrides={},
                output=Path("tree.glb"),
                species=name,
            )
        except ConfigError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
        return JSONResponse(content=config_to_dict_for_ui(cfg))

    @app.post("/api/generate")
    async def post_generate(request: Request):
        payload = await request.json()
        try:
            cfg = load_config(
                yaml_path=None,
                cli_overrides=config_dict_to_overrides(payload),
                output=Path("tree.glb"),
            )
        except ConfigError as e:
            logger.warning("generate: config error: %s", e)
            return JSONResponse(status_code=400, content={"error": str(e)})
        t0 = time.perf_counter()
        try:
            tree = await asyncio.to_thread(simulate, cfg)
            mesh = build_mesh(tree, cfg)
            data = write_glb_to_bytes(mesh, asset_meta={"seed": cfg.seed})
        except ExportError as e:
            logger.warning("generate: export error: %s", e)
            return JSONResponse(status_code=400, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            logger.exception("generate: unexpected error")
            return JSONResponse(
                status_code=500,
                content={"error": f"{type(e).__name__}: {e}"},
            )
        n_tris = sum(p.indices.shape[0] // 3 for p in mesh.primitives)
        logger.info("generate: %.2fs, %d triangles, %d bytes",
                    time.perf_counter() - t0, n_tris, len(data))
        return Response(content=data, media_type="model/gltf-binary")

    @app.post("/api/save-yaml")
    async def post_save_yaml(request: Request):
        payload = await request.json()
        try:
            cfg = load_config(
                yaml_path=None,
                cli_overrides=config_dict_to_overrides(payload),
                output=Path("tree.glb"),
            )
        except ConfigError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
        text = yaml.safe_dump(config_to_dict_for_ui(cfg), sort_keys=False)
        return Response(
            content=text,
            media_type="application/x-yaml",
            headers={"Content-Disposition": 'attachment; filename="tree.yaml"'},
        )

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    def get_root() -> FileResponse:
        return FileResponse(str(static_dir / "index.html"))

    return app
