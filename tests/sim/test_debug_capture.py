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


def test_frames_capture_killed_buds_and_shed(tmp_path):
    cfg = _tiny_cfg(tmp_path)
    forest = build_forest(cfg)
    c = DebugCollector()
    c.capture_static(forest, cfg)
    # Kill three markers, then capture a frame: killed indices are exactly those.
    killed_pts = forest.markers.positions[[5, 6, 7]]
    forest.markers.kill_near(killed_pts, kill_radius=0.001)
    c.capture_frame(forest, t=1.0)
    frame = c.timeline()["frames"][0]
    assert frame["t"] == 1.0
    assert set(frame["markers_killed"]) == {5, 6, 7}
    # Buds come from each tree's active_buds, flattened, with a string state.
    n_active = sum(len(tr.active_buds) for tr in forest.trees)
    assert len(frame["buds"]) == n_active
    if frame["buds"]:
        assert frame["buds"][0]["state"] in ("ACTIVE", "DORMANT", "RESERVE", "DEAD")
        assert len(frame["buds"][0]["p"]) == 3
        assert len(frame["buds"][0]["dir"]) == 3
    # No internodes removed yet -> no shed.
    assert frame["shed"] == []


def test_markers_killed_is_a_partition_across_frames(tmp_path):
    cfg = _tiny_cfg(tmp_path)
    forest = build_forest(cfg)
    c = DebugCollector()
    c.capture_static(forest, cfg)
    # Frame 1: kill markers {0,1}. Frame 2: kill markers {1,2} (1 already dead).
    c_before = forest.markers.alive_mask()
    forest.markers.kill_near(forest.markers.positions[[0, 1]], kill_radius=0.001)
    c.capture_frame(forest, t=1.0)
    forest.markers.kill_near(forest.markers.positions[[1, 2]], kill_radius=0.001)
    c.capture_frame(forest, t=2.0)
    frames = c.timeline()["frames"]
    f1 = set(frames[0]["markers_killed"])
    f2 = set(frames[1]["markers_killed"])
    assert f1 == {0, 1}
    # Frame 2 only reports the NEWLY dead marker (2), not the already-dead 1.
    assert f2 == {2}
    assert f1.isdisjoint(f2)
    assert c_before.all()  # sanity: started all-alive


def test_shed_reports_removed_internode_endpoints(tmp_path):
    cfg = _tiny_cfg(tmp_path)
    forest = build_forest(cfg)
    c = DebugCollector()
    c.capture_static(forest, cfg)
    # Synthesize an internode, capture a baseline frame, then remove it.
    from palubicki.sim.tree import Internode, Node
    tree = forest.trees[0]
    n0, n1 = Node(position=np.array([0.0, 0.0, 0.0])), Node(position=np.array([0.0, 1.0, 0.0]))
    iod = Internode(parent_node=n0, child_node=n1, length=1.0, is_main_axis=True)
    tree.all_internodes.append(iod)
    c.capture_frame(forest, t=1.0)               # iod present this frame
    tree.all_internodes.remove(iod)
    c.capture_frame(forest, t=2.0)               # iod gone -> shed
    frame2 = c.timeline()["frames"][1]
    assert [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]] in frame2["shed"]
