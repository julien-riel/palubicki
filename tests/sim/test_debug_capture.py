import numpy as np

from palubicki.config import load_config
from palubicki.sim.debug_capture import DebugCollector
from palubicki.sim.forest import build_forest


def _tiny_cfg(tmp_path):
    return load_config(
        yaml_path=None,
        cli_overrides={
            "envelope.shape": "ellipsoid",
            "envelope.rx": 1.0,
            "envelope.ry": 2.0,
            "envelope.rz": 1.0,
            "envelope.marker_count": 150,
            "sim.max_simulation_years": 4,
            "seed": 1,
        },
        output=tmp_path / "tree.glb",
    )


def test_capture_static_records_envelope_and_all_marker_positions(tmp_path):
    cfg = _tiny_cfg(tmp_path)
    forest = build_forest(cfg)
    c = DebugCollector()
    c.capture_static(forest, cfg)
    tl = c.timeline()
    assert tl["envelope"]["shape"] == "ellipsoid"
    assert tl["envelope"]["radii"] == [1.0, 2.0, 1.0]
    assert len(tl["envelope"]["center"]) == 3
    # Every marker position is present exactly once, sent statically.
    assert len(tl["markers"]["positions"]) == len(forest.markers.positions)
    assert tl["frames"] == []
