"""Convert between nested config JSON (UI <-> wire format) and flat dotted overrides."""
from __future__ import annotations

from typing import Any

from palubicki.config import Config
from palubicki.cli import _config_to_dict


def config_to_dict_for_ui(cfg: Config) -> dict:
    """Same shape as `palubicki dump-defaults` output. Re-uses cli helper."""
    return _config_to_dict(cfg)


def config_dict_to_overrides(d: dict) -> dict:
    """Flatten a nested config dict into dotted-key overrides.

    None values are dropped (they represent "use default"); nested dicts are
    recursed into. Non-dict values become leaves keyed by the dotted path.
    """
    out: dict[str, Any] = {}
    _flatten(d, "", out)
    return out


def _flatten(node: dict, prefix: str, out: dict) -> None:
    for k, v in node.items():
        key = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        if v is None:
            continue
        if isinstance(v, dict):
            _flatten(v, key, out)
        else:
            out[key] = v
