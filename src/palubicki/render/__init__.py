# src/palubicki/render/__init__.py
"""Headless PNG rendering for palubicki Mesh / .glb (diagnostic level).

Matplotlib is an optional dependency: install with `pip install -e '.[render]'`.
Importing this module does NOT import matplotlib. The matplotlib import is
deferred to render_mesh() / render_glb() — failures raise RenderDependencyError.
"""
from __future__ import annotations


class RenderError(Exception):
    """Generic render module failure (bad input, degenerate mesh, etc.)."""


class RenderDependencyError(RenderError):
    """Raised when an optional dep (matplotlib) is missing."""


def render_mesh(mesh, **kwargs):
    """See palubicki.render.renderer.render_mesh."""
    from palubicki.render.renderer import render_mesh as _impl
    return _impl(mesh, **kwargs)


__all__ = ["RenderError", "RenderDependencyError", "render_mesh"]
