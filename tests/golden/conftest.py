# tests/golden/conftest.py
import pytest


@pytest.fixture
def update_goldens(request):
    return request.config.getoption("--update-goldens")


@pytest.fixture
def render_on_fail(request):
    return request.config.getoption("--render-on-fail")
