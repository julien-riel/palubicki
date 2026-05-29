# tests/golden/test_goldens.py
import hashlib
from pathlib import Path

import numpy as np
import pygltflib
import pytest

from palubicki.config import (
    Config,
    EnvelopeConfig,
    GeomConfig,
    LightConfig,
    PhyllotaxyConfig,
    SheddingConfig,
    SimConfig,
    TropismConfig,
)
from palubicki.export.gltf import write_glb
from palubicki.geom.builder import build_mesh
from palubicki.sim.simulator import simulate

GOLDEN_DIR = Path(__file__).parent / "data"
pytestmark = pytest.mark.slow


def _cfg_ellipsoid(out: Path) -> Config:
    return Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=600),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1, max_simulation_years=10.0),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        seed=7,
        output=out,
    )


def _hash_buffers(glb_path: Path) -> str:
    loaded = pygltflib.GLTF2().load(str(glb_path))
    sha = hashlib.sha256()
    for prim in loaded.meshes[0].primitives:
        for acc_idx in (prim.attributes.POSITION, prim.attributes.NORMAL,
                        prim.attributes.TEXCOORD_0, prim.attributes.COLOR_0,
                        prim.indices):
            if acc_idx is None:
                continue
            acc = loaded.accessors[acc_idx]
            bv = loaded.bufferViews[acc.bufferView]
            blob = loaded.binary_blob()[bv.byteOffset : bv.byteOffset + bv.byteLength]
            sha.update(blob)
    return sha.hexdigest()


def _cfg_ellipsoid_light(out: Path) -> Config:
    return Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=600),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1, max_simulation_years=8.0),
        tropism=TropismConfig(w_phototropism=0.3),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        light=LightConfig(enabled=True, grid_resolution=(24, 32, 24), n_rays=8, k_absorption=0.5),
        seed=7,
        output=out,
    )


def test_golden_ellipsoid(tmp_path, update_goldens, render_on_fail):
    cfg = _cfg_ellipsoid(tmp_path / "g.glb")
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    write_glb(mesh, cfg.output, asset_meta={"seed": cfg.seed})

    h = _hash_buffers(cfg.output)
    golden = GOLDEN_DIR / "ellipsoid.sha256"

    if update_goldens or not golden.exists():
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden.write_text(h)
        pytest.skip("golden written; re-run without --update-goldens to verify")
    expected = golden.read_text().strip()

    if h != expected and render_on_fail:
        diff_dir = tmp_path / "diff"
        diff_dir.mkdir(exist_ok=True)
        try:
            from palubicki.render import render_mesh, save_png
            save_png(render_mesh(mesh, size=(600, 600)), diff_dir / "actual.png")
            extra = f"\n  rendered actual to: {diff_dir / 'actual.png'}"
        except Exception as e:  # render is best-effort, never block the assert
            extra = f"\n  (render-on-fail unavailable: {e})"
    else:
        extra = ""

    assert h == expected, (
        f"golden mismatch.\nexpected: {expected}\nactual:   {h}\n"
        f"if intentional, re-run with --update-goldens after visual review{extra}"
    )


def test_golden_ellipsoid_light(tmp_path, update_goldens):
    cfg = _cfg_ellipsoid_light(tmp_path / "g_light.glb")
    tree = simulate(cfg)
    mesh = build_mesh(tree, cfg)
    write_glb(mesh, cfg.output, asset_meta={"seed": cfg.seed, "light_enabled": True})

    h = _hash_buffers(cfg.output)
    golden = GOLDEN_DIR / "ellipsoid_light.sha256"

    if update_goldens or not golden.exists():
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden.write_text(h)
        pytest.skip("golden written; re-run without --update-goldens to verify")
    expected = golden.read_text().strip()
    assert h == expected, (
        f"golden mismatch.\nexpected: {expected}\nactual:   {h}\n"
        f"if intentional, re-run with --update-goldens after visual review"
    )


@pytest.mark.slow
def test_golden_forest_v3(tmp_path):
    """Pin a hash for a deterministic V3 forest run."""
    import hashlib
    import json

    from palubicki.config import (
        Config,
        EnvelopeConfig,
        ForestConfig,
        ForestSeed,
        GeomConfig,
        LightConfig,
        ObstacleAABB,
        PhyllotaxyConfig,
        SheddingConfig,
        SimConfig,
        TropismConfig,
    )
    from palubicki.sim.simulator import simulate_forest

    cfg = Config(
        envelope=EnvelopeConfig(rx=1.5, ry=2.5, rz=1.5, shape="ellipsoid", marker_count=2000),
        sim=SimConfig(max_simulation_years=10.0),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(),
        light=LightConfig(enabled=True),
        output=tmp_path / "x.glb", seed=42,
        forest=ForestConfig(
            seeds=(
                ForestSeed(position=(0.0, 0.0, 0.0)),
                ForestSeed(position=(4.0, 0.0, 0.0)),
                ForestSeed(position=(2.0, 0.0, 3.0)),
            ),
            obstacles=(ObstacleAABB(min=(1.5, 0.0, -1.0), max=(2.5, 2.0, 1.0)),),
        ),
    )
    forest = simulate_forest(cfg)
    positions = []
    for tree_index, tree in enumerate(forest.trees):
        stack = [tree.root]
        while stack:
            node = stack.pop()
            positions.append((tree_index, tuple(np.round(node.position, 6).tolist())))
            for iod in node.children_internodes:
                stack.append(iod.child_node)
    digest = hashlib.sha256(json.dumps(sorted(positions), sort_keys=True, default=list).encode()).hexdigest()
    # Re-pinned for #24: phyllotaxy divergence now advances per-axis
    # (Bud.axis_node_ordinal) instead of the global, interleaved node_index, so
    # lateral bud directions — and thus the whole forest geometry — change.
    EXPECTED = "deaef41f96739f039175f4add9ea97f6aede3e6e58f2bc6a2bea6fee675fa471"
    if EXPECTED is not None:
        assert digest == EXPECTED, f"V3 forest hash drifted: {digest}"
    print(f"V3 forest golden hash: {digest}")
