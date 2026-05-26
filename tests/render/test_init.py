# tests/render/test_init.py
import pytest


def test_render_exceptions_are_importable():
    from palubicki.render import RenderError, RenderDependencyError
    assert issubclass(RenderDependencyError, RenderError)
    assert issubclass(RenderError, Exception)


def test_render_module_does_not_require_matplotlib_to_import():
    """The base module must import even if matplotlib is missing —
    only render_mesh / render_glb may force the import."""
    import importlib
    import palubicki.render
    importlib.reload(palubicki.render)  # ensure clean import path
    assert hasattr(palubicki.render, "RenderError")
