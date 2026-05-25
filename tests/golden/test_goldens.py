# tests/golden/test_goldens.py
import hashlib
from pathlib import Path

import numpy as np
import pygltflib
import pytest

from palubicki.config import (
    Config, EnvelopeConfig, GeomConfig, PhyllotaxyConfig,
    SheddingConfig, SimConfig, TropismConfig,
)
from palubicki.export.gltf import write_glb
from palubicki.geom.builder import build_mesh
from palubicki.sim.simulator import simulate

GOLDEN_DIR = Path(__file__).parent / "data"
pytestmark = pytest.mark.slow


def _cfg_ellipsoid(out: Path) -> Config:
    return Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=600),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1, max_iterations=10),
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
                        prim.attributes.TEXCOORD_0, prim.indices):
            acc = loaded.accessors[acc_idx]
            bv = loaded.bufferViews[acc.bufferView]
            blob = loaded.binary_blob()[bv.byteOffset : bv.byteOffset + bv.byteLength]
            sha.update(blob)
    return sha.hexdigest()


def test_golden_ellipsoid(tmp_path, update_goldens):
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
    assert h == expected, (
        f"golden mismatch.\nexpected: {expected}\nactual:   {h}\n"
        f"if intentional, re-run with --update-goldens after visual review"
    )
