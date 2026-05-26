# src/palubicki/render/errors.py
"""Exception types for palubicki.render.

Lives outside __init__.py so other modules in the package (renderer, camera,
io) can import exceptions without triggering the lazy public-API wrappers.
"""
from __future__ import annotations


class RenderError(Exception):
    """Generic render module failure (bad input, degenerate mesh, etc.)."""


class RenderDependencyError(RenderError):
    """Raised when an optional dep (matplotlib) is missing."""
