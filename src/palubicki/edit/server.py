"""FastAPI app for the browser-based tree parameter editor."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from palubicki.config import Config, ConfigError, _load_packaged_species
from palubicki.edit.config_io import config_to_dict_for_ui
from palubicki.edit.schema import build_schema


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

    return app
