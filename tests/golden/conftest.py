# tests/golden/conftest.py
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--update-goldens", action="store_true",
        help="Regenerate golden binaries instead of comparing.",
    )


@pytest.fixture
def update_goldens(request):
    return request.config.getoption("--update-goldens")
