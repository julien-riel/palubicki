import numpy as np
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--update-goldens", action="store_true",
        help="Regenerate golden binaries instead of comparing.",
    )


@pytest.fixture
def rng():
    return np.random.default_rng(42)
