
import numpy as np
import pygltflib

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
from palubicki.export.gltf import write_glb_forest
from palubicki.sim.simulator import simulate_forest


def _cfg(tmp_path, seeds, *, obstacles=(), export_obstacles=False, light=False):
    """Small, fast forest config for export tests."""
    return Config(
        envelope=EnvelopeConfig(rx=1.5, ry=2.5, rz=1.5, shape="ellipsoid", marker_count=1000),
        sim=SimConfig(max_simulation_years=4.0),
        tropism=TropismConfig(), phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(), geom=GeomConfig(), light=LightConfig(enabled=light),
        output=tmp_path / "scene.glb", seed=42,
        forest=ForestConfig(seeds=tuple(seeds), obstacles=tuple(obstacles),
                            export_obstacles_geometry=export_obstacles),
    )


def _instance_count(node) -> int:
    """Number of tree instances a node represents: 1 for a plain TRS node, N for
    an EXT_mesh_gpu_instancing node (from its TRANSLATION featureCount)."""
    ext = (node.extensions or {}).get("EXT_mesh_gpu_instancing")
    if ext is None:
        return 1
    feats = (node.extensions or {}).get("EXT_instance_features", {}).get("featureIds", [])
    return int(feats[0]["featureCount"])


# --------------------------------------------------------------------------- #
# scene structure (kept from the pre-instancing exporter)
# --------------------------------------------------------------------------- #

def test_write_glb_forest_has_one_node_per_tree(tmp_path):
    # Distinct derived seeds (42+0, 42+1) -> distinct geometry -> instance-of-one.
    cfg = _cfg(tmp_path, [ForestSeed(position=(0.0, 0.0, 0.0)),
                          ForestSeed(position=(8.0, 0.0, 0.0))])
    forest = simulate_forest(cfg)
    write_glb_forest(forest, cfg, tmp_path / "scene.glb", asset_meta={"seed": 42})

    loaded = pygltflib.GLTF2().load(str(tmp_path / "scene.glb"))
    names = [n.name for n in loaded.nodes]
    assert "tree_0" in names
    assert "tree_1" in names


def test_write_glb_forest_includes_obstacles_node(tmp_path):
    cfg = _cfg(tmp_path, [ForestSeed(position=(0.0, 0.0, 0.0))],
               obstacles=[ObstacleAABB(min=(3, 0, -1), max=(4, 2, 1))], export_obstacles=True)
    forest = simulate_forest(cfg)
    write_glb_forest(forest, cfg, tmp_path / "scene.glb", asset_meta={"seed": 42})

    loaded = pygltflib.GLTF2().load(str(tmp_path / "scene.glb"))
    names = [n.name for n in loaded.nodes]
    assert "obstacles" in names


def test_write_glb_forest_embeds_config_in_asset_extras(tmp_path):
    cfg = _cfg(tmp_path, [ForestSeed(position=(0.0, 0.0, 0.0))])
    forest = simulate_forest(cfg)
    write_glb_forest(
        forest, cfg, tmp_path / "scene.glb",
        asset_meta={"seed": 42, "config": {"forest": {"seeds": [{"position": [0, 0, 0]}]}}},
    )

    loaded = pygltflib.GLTF2().load(str(tmp_path / "scene.glb"))
    extras = loaded.asset.extras or {}
    assert "config" in extras


# --------------------------------------------------------------------------- #
# P0: unit-tree-at-origin + per-instance transforms (#71)
# --------------------------------------------------------------------------- #

def test_unit_tree_not_world_baked(tmp_path):
    """A tree placed at world x=40 must keep its vertices at the LOCAL origin and
    carry its world position on the node transform — never baked into the verts."""
    cfg = _cfg(tmp_path, [ForestSeed(position=(0.0, 0.0, 0.0)),
                          ForestSeed(position=(40.0, 0.0, 0.0))])
    forest = simulate_forest(cfg)
    write_glb_forest(forest, cfg, tmp_path / "scene.glb", asset_meta={"seed": 42})
    g = pygltflib.GLTF2().load(str(tmp_path / "scene.glb"))

    by_name = {n.name: n for n in g.nodes}
    far = by_name["tree_1"]
    assert far.translation == [40.0, 0.0, 0.0]
    # Every primitive of the far tree is centred near the local origin (within a
    # crown radius), NOT shifted out to world x~40.
    for prim in g.meshes[far.mesh].primitives:
        acc = g.accessors[prim.attributes.POSITION]
        assert acc.min[0] > -5.0 and acc.max[0] < 5.0, (acc.min, acc.max)


def test_instance_count_equals_tree_count(tmp_path):
    cfg = _cfg(tmp_path, [ForestSeed(position=(0.0, 0.0, 0.0)),
                          ForestSeed(position=(8.0, 0.0, 0.0)),
                          ForestSeed(position=(16.0, 0.0, 0.0))])
    forest = simulate_forest(cfg)
    write_glb_forest(forest, cfg, tmp_path / "scene.glb", asset_meta={"seed": 42})
    g = pygltflib.GLTF2().load(str(tmp_path / "scene.glb"))

    tree_nodes = [n for n in g.nodes if n.name != "obstacles"]
    assert sum(_instance_count(n) for n in tree_nodes) == len(forest.trees)
    # Distinct seeds -> no sharing -> all instance-of-one -> no instancing ext.
    assert not g.extensionsUsed
    assert all((n.extensions or {}).get("EXT_mesh_gpu_instancing") is None for n in tree_nodes)


def test_singleton_node_carries_metadata_extras(tmp_path):
    cfg = _cfg(tmp_path, [ForestSeed(position=(0.0, 0.0, 0.0), species="oak")])
    forest = simulate_forest(cfg)
    write_glb_forest(forest, cfg, tmp_path / "scene.glb", asset_meta={"seed": 42})
    g = pygltflib.GLTF2().load(str(tmp_path / "scene.glb"))

    node = next(n for n in g.nodes if n.name == "tree_0")
    assert node.extras["species"] == "oak"
    assert "seed" in node.extras


def test_identical_trees_share_one_instanced_mesh(tmp_path):
    """Geometrically-identical trees (same explicit seed, far enough apart that
    they neither overlap nor compete) collapse to ONE mesh under a single
    EXT_mesh_gpu_instancing node carrying every placement."""
    n = 4
    seeds = [ForestSeed(position=(30.0 * k, 0.0, 0.0), seed=7) for k in range(n)]
    cfg = _cfg(tmp_path, seeds)
    forest = simulate_forest(cfg)
    write_glb_forest(forest, cfg, tmp_path / "scene.glb", asset_meta={"seed": 42})
    g = pygltflib.GLTF2().load(str(tmp_path / "scene.glb"))

    assert g.asset.extras["instancing"]["n_meshes"] == 1
    assert g.asset.extras["instancing"]["n_instances"] == n
    assert g.extensionsUsed == ["EXT_mesh_gpu_instancing", "EXT_instance_features"]

    tree_nodes = [nd for nd in g.nodes if nd.name != "obstacles"]
    assert len(tree_nodes) == 1
    node = tree_nodes[0]
    inst = node.extensions["EXT_mesh_gpu_instancing"]
    t_acc = g.accessors[inst["attributes"]["TRANSLATION"]]
    assert t_acc.count == n
    assert t_acc.type == "VEC3"
    # The four placements are exactly the seed positions.
    blob = g.binary_blob()
    bv = g.bufferViews[t_acc.bufferView]
    trans = np.frombuffer(blob, dtype=np.float32,
                          count=n * 3, offset=bv.byteOffset).reshape(n, 3)
    got = sorted(round(float(x), 3) for x in trans[:, 0])
    assert got == [0.0, 30.0, 60.0, 90.0]
    # Instance-attribute bufferViews must not declare an ARRAY_BUFFER target.
    assert bv.target is None
    # EXT_instance_features declares the species/seed feature IDs.
    feats = node.extensions["EXT_instance_features"]["featureIds"]
    assert [f["label"] for f in feats] == ["species", "seed"]
    assert all(f["featureCount"] == n for f in feats)


def test_repeated_species_file_size_sub_linear(tmp_path):
    """Eight identical trees must not cost eight trees' worth of bytes."""
    one = _cfg(tmp_path, [ForestSeed(position=(0.0, 0.0, 0.0), seed=7)])
    one_path = tmp_path / "one.glb"
    write_glb_forest(simulate_forest(one), one, one_path, asset_meta={"seed": 42})

    many = _cfg(tmp_path, [ForestSeed(position=(30.0 * k, 0.0, 0.0), seed=7) for k in range(8)])
    many_path = tmp_path / "many.glb"
    write_glb_forest(simulate_forest(many), many, many_path, asset_meta={"seed": 42})

    s1 = one_path.stat().st_size
    s8 = many_path.stat().st_size
    # Sharing means geometry is stored once; the delta is just instance buffers.
    assert s8 < 1.5 * s1, (s1, s8)


def test_trimesh_roundtrip_places_trees(tmp_path):
    """The single-transform (instance-of-one) path round-trips through trimesh
    with trees at their world positions, not stacked at the origin."""
    trimesh = __import__("trimesh")
    cfg = _cfg(tmp_path, [ForestSeed(position=(0.0, 0.0, 0.0)),
                          ForestSeed(position=(40.0, 0.0, 0.0))])
    forest = simulate_forest(cfg)
    write_glb_forest(forest, cfg, tmp_path / "scene.glb", asset_meta={"seed": 42})

    scene = trimesh.load(str(tmp_path / "scene.glb"), force="scene")
    lo, hi = scene.bounds
    # One tree near x=0, one near x=40 -> the scene spans the full separation.
    assert lo[0] < 5.0
    assert hi[0] > 35.0
