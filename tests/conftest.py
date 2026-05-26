import numpy as np
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--update-goldens", action="store_true",
        help="Regenerate golden binaries instead of comparing.",
    )
    parser.addoption(
        "--render-on-fail", action="store_true",
        help="When a golden buffer hash check fails, also render PNG of the "
             "current mesh to tmp_path/diff/ for visual diagnosis.",
    )


@pytest.fixture
def rng():
    return np.random.default_rng(42)
