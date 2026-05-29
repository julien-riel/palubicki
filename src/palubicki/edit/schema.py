"""Introspect Config dataclasses to drive auto-generated UI controls."""
from __future__ import annotations

from dataclasses import MISSING, fields
from typing import Any, Literal, get_args, get_origin, get_type_hints

from palubicki.config import (
    Config,
    EnvelopeConfig,
    GeomConfig,
    LightConfig,
    PhyllotaxyConfig,
    SagConfig,
    SheddingConfig,
    SimConfig,
    TropismConfig,
    _list_species,
)

_SECTIONS: list[tuple[str, type, str]] = [
    ("envelope", EnvelopeConfig, "Envelope"),
    ("sim", SimConfig, "Simulation"),
    ("tropism", TropismConfig, "Tropism"),
    ("phyllotaxy", PhyllotaxyConfig, "Phyllotaxy"),
    ("shedding", SheddingConfig, "Shedding"),
    ("geom", GeomConfig, "Geometry"),
    ("light", LightConfig, "Light"),
    ("sag", SagConfig, "Sag"),
]


def build_schema() -> dict:
    """Build the JSON schema sent to the browser to drive the UI."""
    sections: list[dict] = []
    for name, cls, label in _SECTIONS:
        hints = get_type_hints(cls)
        descriptors: list[dict] = []
        for f in fields(cls):
            ui = f.metadata.get("ui")
            if ui is None:
                continue
            descriptors.append(_field_descriptor(f, hints[f.name], ui))
        if descriptors:
            sections.append({"name": name, "label": label, "fields": descriptors})

    top_hints = get_type_hints(Config)
    top_fields: list[dict] = []
    for f in fields(Config):
        if f.name in {s[0] for s in _SECTIONS} or f.name == "forest":
            continue
        ui = f.metadata.get("ui")
        if ui is None:
            continue
        top_fields.append(_field_descriptor(f, top_hints[f.name], ui))

    return {
        "sections": sections,
        "top_level": top_fields,
        "species": _list_species(),
    }


def _field_descriptor(f, annotation: Any, ui: dict) -> dict:
    default = f.default if f.default is not MISSING else None
    if isinstance(default, tuple):
        default = list(default)
    return {
        "name": f.name,
        "default": default,
        **_type_info(annotation),
        **{k: v for k, v in ui.items() if k != "type"},
    }


def _type_info(annotation: Any) -> dict:
    if annotation is int:
        return {"type": "int"}
    if annotation is float:
        return {"type": "float"}
    if annotation is bool:
        return {"type": "bool"}
    origin = get_origin(annotation)
    if origin is Literal:
        return {"type": "enum", "choices": list(get_args(annotation))}
    if origin is tuple:
        args = get_args(annotation)
        if len(args) == 3 and all(a is float for a in args):
            return {"type": "vec3"}
        if len(args) == 3 and all(a is int for a in args):
            return {"type": "ivec3"}
    return {"type": "unknown"}
