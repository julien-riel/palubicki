import hashlib
from pathlib import Path

import pygltflib
import pytest

from palubicki.cli import main

GOLDEN_DIR = Path(__file__).parent / "data"
pytestmark = pytest.mark.slow


def _hash_buffers(glb_path: Path) -> str:
    """Hash all primitive buffer data (positions, normals, uvs, indices) for stability
    across runs that share the same simulation output."""
    loaded = pygltflib.GLTF2().load(str(glb_path))
    sha = hashlib.sha256()
    for mesh in loaded.meshes:
        for prim in mesh.primitives:
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


@pytest.mark.parametrize("species", ["oak", "pine", "birch", "maple", "fir"])
def test_species_golden(tmp_path, update_goldens, species):
    out = tmp_path / f"{species}.glb"
    # Render at each preset's OWN marker_count (its calibrated design density),
    # not a flat --marker-count 1000. #43 enlarged the conifer envelopes ~6.5x;
    # at 1000 markers that density collapses ~18x below design and the strict
    # monopodial conifer leaders STARVE (pine main_axis_continuation_rate -> 0.10,
    # a decapitated stub) or arch on noisy perception (birch leader deviation
    # -> 45deg). That was the #48 "regression" — an artifact of the proxy
    # under-sampling the presets, not a defect in the presets themselves (at
    # design density all three render as upright young conifers). Keep --years 10
    # so the tree stays young and the test stays fast; density is what the
    # geometry gate must reproduce faithfully.
    rc = main([
        "generate", "--species", species,
        "--seed", "42",
        "--years", "10",
        "-o", str(out),
    ])
    assert rc == 0

    h = _hash_buffers(out)
    golden = GOLDEN_DIR / f"species_{species}.sha256"
    if update_goldens or not golden.exists():
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden.write_text(h)
        pytest.skip(f"golden written for {species}; re-run without --update-goldens to verify")

    expected = golden.read_text().strip()
    assert h == expected, (
        f"golden mismatch for {species}.\nexpected: {expected}\nactual:   {h}\n"
        f"if intentional (after preset tuning), re-run with --update-goldens after visual review"
    )
