# tests/golden/conftest.py
import pytest


@pytest.fixture
def update_goldens(request):
    return request.config.getoption("--update-goldens")
