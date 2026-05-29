# tests/render/test_init.py


def test_render_exceptions_are_importable():
    from palubicki.render import RenderDependencyError, RenderError
    assert issubclass(RenderDependencyError, RenderError)
    assert issubclass(RenderError, Exception)


def test_render_module_does_not_require_matplotlib_to_import():
    """Importing palubicki.render must NOT eager-import matplotlib.
    The matplotlib import is deferred to render_mesh / render_glb."""
    import sys
    # Force a clean re-import so a previously cached palubicki.render
    # (which may have been loaded after matplotlib in this session) is
    # not what we test against.
    sys.modules.pop("palubicki.render", None)
    sys.modules.pop("matplotlib", None)
    import palubicki.render  # noqa: F401
    assert "matplotlib" not in sys.modules, (
        "palubicki.render eager-imported matplotlib; it must stay lazy"
    )
