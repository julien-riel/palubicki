# src/palubicki/render/__init__.py
"""Headless PNG rendering for palubicki Mesh / .glb (diagnostic level).

Matplotlib is an optional dependency: install with `pip install -e '.[render]'`.
Importing this module does NOT import matplotlib. The matplotlib import is
deferred to render_mesh() / render_glb() — failures raise RenderDependencyError.
"""
from __future__ import annotations

from palubicki.render.errors import RenderDependencyError, RenderError


def render_mesh(mesh, **kwargs):
    """See palubicki.render.renderer.render_mesh."""
    from palubicki.render.renderer import render_mesh as _impl
    return _impl(mesh, **kwargs)


def render_glb(glb_path, **kwargs):
    """See palubicki.render.renderer.render_glb."""
    from palubicki.render.renderer import render_glb as _impl
    return _impl(glb_path, **kwargs)


def save_png(image, path):
    """See palubicki.render.io.save_png."""
    from palubicki.render.io import save_png as _impl
    return _impl(image, path)


# Camera is small and matplotlib-free; eager export is fine.
from palubicki.render.camera import Camera  # noqa: E402

__all__ = [
    "Camera",
    "RenderError",
    "RenderDependencyError",
    "render_mesh",
    "render_glb",
    "save_png",
]
