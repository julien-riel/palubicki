"""P2 photoreal-master material emission: normal/ORM slots, color-management
contract, and the KHR_* extensions (texture_transform, specular,
diffuse_transmission, materials_variants)."""
import numpy as np
import pygltflib
import pytest

from palubicki.export.gltf import write_glb_to_bytes
from palubicki.geom.mesh import Material, Mesh, Primitive, TextureTransform

# A 1×1 PNG is enough — these tests assert the glTF wiring, not pixel content.
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _quad(material, **prim_kw):
    pos = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float32)
    nrm = np.tile(np.array([0, 0, 1], np.float32), (4, 1))
    uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
    idx = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
    return Primitive(positions=pos, normals=nrm, uvs=uv, indices=idx, material=material, **prim_kw)


def _full_material(**kw):
    base = {
        "name": "leaf", "base_color": (0.4, 0.6, 0.2, 1.0), "metallic": 0.0, "roughness": 0.8,
        "base_color_texture_png": _PNG, "alpha_mode": "MASK", "alpha_cutoff": 0.5,
        "double_sided": True, "normal_texture_png": _PNG, "normal_scale": 1.3,
        "orm_texture_png": _PNG, "occlusion_strength": 0.9, "specular_factor": 0.35,
        "transmission_texture_png": _PNG, "diffuse_transmission_factor": 0.55,
        "diffuse_transmission_color": (0.5, 0.65, 0.25),
    }
    base.update(kw)
    return Material(**base)


def _load(prim) -> pygltflib.GLTF2:
    data = write_glb_to_bytes(Mesh(primitives=[prim]), asset_meta={})
    return pygltflib.GLTF2().load_from_bytes(data)


def test_orm_one_image_two_slots():
    """The packed ORM image feeds BOTH metallicRoughnessTexture (G,B) and
    occlusionTexture (R) — one image, two slots."""
    g = _load(_quad(_full_material()))
    mat = g.materials[0]
    mr = mat.pbrMetallicRoughness.metallicRoughnessTexture.index
    occ = mat.occlusionTexture.index
    assert mr == occ
    assert mat.occlusionTexture.strength == pytest.approx(0.9)


def test_normal_slot_and_scale():
    g = _load(_quad(_full_material()))
    nt = g.materials[0].normalTexture
    assert nt is not None
    assert nt.scale == pytest.approx(1.3)
    # base colour, normal and ORM are distinct images on distinct slots.
    assert nt.index != g.materials[0].pbrMetallicRoughness.baseColorTexture.index


def test_color_management_slots():
    """Color space is implied by slot: base colour rides baseColorTexture (sRGB),
    everything linear (normal/ORM) rides its own linear slot — never baseColor."""
    g = _load(_quad(_full_material()))
    mat = g.materials[0]
    base = mat.pbrMetallicRoughness.baseColorTexture.index
    assert mat.normalTexture.index != base
    assert mat.pbrMetallicRoughness.metallicRoughnessTexture.index != base
    assert mat.occlusionTexture.index != base


def test_specular_extension():
    g = _load(_quad(_full_material()))
    ext = g.materials[0].extensions["KHR_materials_specular"]
    assert ext["specularFactor"] == pytest.approx(0.35)
    assert "KHR_materials_specular" in g.extensionsUsed


def test_diffuse_transmission_extension_metadata():
    g = _load(_quad(_full_material()))
    dt = g.materials[0].extensions["KHR_materials_diffuse_transmission"]
    assert dt["diffuseTransmissionFactor"] == pytest.approx(0.55)
    assert dt["diffuseTransmissionColorFactor"] == pytest.approx([0.5, 0.65, 0.25])
    assert "index" in dt["diffuseTransmissionTexture"]
    assert "KHR_materials_diffuse_transmission" in g.extensionsUsed


def test_no_maps_no_extensions():
    """A plain material (no maps) emits no slots and no extensionsUsed — the P2
    machinery is fully opt-in per material."""
    plain = Material(name="bark", base_color=(0.3, 0.2, 0.1, 1.0), metallic=0.0, roughness=0.9,
                     base_color_texture_png=None, alpha_mode="OPAQUE", alpha_cutoff=0.5,
                     double_sided=False)
    g = _load(_quad(plain))
    mat = g.materials[0]
    assert mat.normalTexture is None
    assert mat.occlusionTexture is None
    assert mat.pbrMetallicRoughness.metallicRoughnessTexture is None
    assert not g.extensionsUsed


def test_texture_transform_on_every_textureinfo():
    xf = TextureTransform(offset=(0.25, 0.5), scale=(0.5, 0.5), rotation=0.0)
    g = _load(_quad(_full_material(texture_transform=xf)))
    mat = g.materials[0]
    bt = mat.pbrMetallicRoughness.baseColorTexture
    assert bt.extensions["KHR_texture_transform"]["offset"] == [0.25, 0.5]
    assert bt.extensions["KHR_texture_transform"]["scale"] == [0.5, 0.5]
    # the transform rides the normal slot too (atlas window is per material).
    assert "KHR_texture_transform" in mat.normalTexture.extensions
    assert "KHR_texture_transform" in g.extensionsUsed


def test_identity_transform_not_emitted():
    g = _load(_quad(_full_material(texture_transform=TextureTransform())))
    bt = g.materials[0].pbrMetallicRoughness.baseColorTexture
    assert not (bt.extensions or {})
    assert "KHR_texture_transform" not in (g.extensionsUsed or [])


def test_material_variants_seasons():
    """KHR_materials_variants: a 'summer'/'autumn' swap declares the variants list
    at the document root and per-primitive mappings; the default material stays
    the variant-unaware fallback."""
    summer = _full_material(name="leaf_summer", base_color=(0.4, 0.6, 0.2, 1.0))
    autumn = _full_material(name="leaf_autumn", base_color=(0.7, 0.4, 0.1, 1.0))
    prim = _quad(summer, material_variants=[("summer", summer), ("autumn", autumn)])
    g = _load(prim)

    root = g.extensions["KHR_materials_variants"]["variants"]
    assert [v["name"] for v in root] == ["summer", "autumn"]
    mappings = g.meshes[0].primitives[0].extensions["KHR_materials_variants"]["mappings"]
    assert len(mappings) == 2
    assert {m["variants"][0] for m in mappings} == {0, 1}
    assert "KHR_materials_variants" in g.extensionsUsed
