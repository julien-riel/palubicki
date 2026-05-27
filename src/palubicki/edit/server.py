"""FastAPI app for the browser-based tree parameter editor."""
from __future__ import annotations

import asyncio
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from palubicki.config import Config, ConfigError, _load_packaged_species, load_config
from palubicki.edit.config_io import config_dict_to_overrides, config_to_dict_for_ui
from palubicki.edit.schema import build_schema
from palubicki.export.gltf import ExportError, write_glb_to_bytes
from palubicki.geom.builder import build_mesh
from palubicki.sim.simulator import simulate


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
            data = _load_packaged_species(name)
        except ConfigError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
        return JSONResponse(content=data)

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
            return JSONResponse(status_code=400, content={"error": str(e)})
        try:
            tree = await asyncio.to_thread(simulate, cfg)
            mesh = build_mesh(tree, cfg)
            data = write_glb_to_bytes(mesh, asset_meta={"seed": cfg.seed})
        except ExportError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                status_code=500,
                content={"error": f"{type(e).__name__}: {e}"},
            )
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

    return app
