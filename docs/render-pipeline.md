# From Plant Graph to 3D Asset: A Rendering & Export Reference

*Companion to [botany/plant-structure.md](./botany/plant-structure.md). That document
maps botany onto **data structures** — the tree of phytomers. This one maps that
graph onto a **renderable, exportable asset**: the geometry, materials, textures,
and performance machinery that decide whether a botanically-correct simulation
actually looks like a plant inside Unreal, Unity, Blender, or a web viewer.*

> **Scope.** Grounded in what palubicki emits today: glTF 2.0 / `.glb` via
> `pygltflib`, PBR metallic-roughness. Code references point at
> `src/palubicki/{geom,export,render}/`. Sections flag, explicitly, what exists
> versus what a production games/archviz pipeline still needs — see the gap
> matrix in §12.

---

## 0. Reconciliation note (2026) — read this first

This reference is sound on *what* the gaps are, but a 2026 survey of the four
target engines (three.js, Blender 4.x, Unreal GLTFCore/Interchange, Unity
glTFast) corrected several **feasibility and priority** assumptions below. The
full design and the phased plan live in
[`export-pipeline-design.md`](./export-pipeline-design.md); the corrections that
override statements later in *this* document:

1. **`KHR_materials_diffuse_transmission` is NOT a usable default (§5.2).** It is
   still a Release Candidate and is unsupported in three.js, Blender, Unreal AND
   Unity as of 2026 — building leaf backlight on it renders flat/opaque
   everywhere. Default to a **thickness/translucency mask + per-engine subsurface
   shader** (Unreal *Two-Sided Foliage*, Unity HDRP *Translucent*); emit the
   extension only as forward-looking, engine-ignored metadata.
2. **`MSFT_lod` is a dead vendor extension (§7.2).** Ignored by three.js,
   Blender, Unreal and Unity. Use it for **web viewers only**; engines use native
   LOD groups, and the full master is kept intact for Unreal-Nanite auto-LOD.
3. **Wind data must ride `COLOR_n`/`TEXCOORD_n`, never `_underscore` custom
   attributes (§9).** three.js and Unity silently drop custom attributes on
   import. Use `COLOR_0=(phase,stiffness,leafMask)` + `TEXCOORD_1=pivot` (float),
   and the consuming material must declare them or Unity strips them.
4. **Normal maps require an explicit `TANGENT` attribute (§4.2), not yet
   exported.** Without it, mirrored UV islands seam. It is nearly free for tubes:
   the parallel-transport frame is already computed and discarded at
   `geom/tubes.py:249-259`. This makes wind (which emits TANGENT) a prerequisite
   for normal maps — hence the plan does wind *before* materials.
5. **The forest path bakes world-space verts today (§7.1).** `write_glb_forest`
   builds full geometry per tree with `node.translation` unused
   (`export/gltf.py`), which defeats instancing. Fix: unit-tree-at-origin +
   `EXT_mesh_gpu_instancing`. Nuance: each tree is uniquely seeded → distinct
   topology, so share a mesh only when configs match, otherwise emit
   **instance-of-one** (a node of count 1 carrying just its world transform).
6. **Impostors need a headless GL backend (§7.3).** `render/renderer.py` is
   matplotlib (screen-space) and cannot bake multi-angle offscreen. Use a
   **hemi-octahedral** atlas (not full-octahedral) via moderngl/pyrender; this is
   the biggest infra risk and is deferred.
7. **Architecture = one canonical uncompressed PNG master + derived target
   profiles** (WEB_UNITY meshopt+KTX2+instancing; UNREAL_DCC uncompressed+PNG+
   import-safe). Unreal reads no Draco/meshopt/KTX2/gpu_instancing, so an
   uncompressed fallback is mandatory, not optional (§8, §12).
8. **Recommended order is resequenced (§12):** forest instancing first (highest
   ROI, independent of texture work), then wind (unblocks normal maps via
   TANGENT), then materials — *not* look-first.

---

## 1. Why a second layer exists

The plant graph is *correct* but it is not an *asset*. A node-and-edge tree of
phytomers carries no triangles, no UVs, no materials, no alpha, no level of
detail, no pivot, no wind rig. The render layer is the lossy projection from
"biologically faithful state" to "something a GPU draws 60 times a second
without choking." Almost every decision here is a **fidelity-vs-budget trade**
that the botany layer never has to make.

Three facts drive the whole layer:

1. **A GPU draws triangles, not topology.** Every branch becomes a swept tube;
   every leaf becomes one or more textured quads (cards). The conversion is in
   `src/palubicki/geom/` — `tubes.py` for bark, `leaves.py` + `leaf_blade.py`
   for foliage.
2. **Foliage is the entire problem.** A tree is 99% leaves by primitive count
   and ~0% leaves by silhouette importance per primitive. How you fake leaves
   (cards + alpha + translucency + LOD) dominates both look and cost. §5.
3. **The same asset ships to wildly different budgets.** A hero archviz tree
   (millions of triangles, ray-traced) and a background game tree (a single
   camera-facing impostor) come from the *same* graph. That fan-out is LOD and
   instancing. §7.

---

## 2. The target format: glTF 2.0 / `.glb`

glTF is the right hub format and palubicki already commits to it
(`src/palubicki/export/gltf.py`, `write_glb_to_bytes`). It is the "JPEG of 3D":
runtime-oriented, PBR-native, imported by every engine, and viewable in the
browser (the project's editor uses three.js `GLTFLoader` —
`src/palubicki/edit/static/vendor/GLTFLoader.js`).

### 2.1 What `.glb` carries

| glTF concept | palubicki type | Code |
|---|---|---|
| `mesh.primitive` (POSITION, NORMAL, TEXCOORD_0, COLOR_0, indices) | `Primitive` | `geom/mesh.py` |
| `material` (PBR metallic-roughness) | `Material` | `geom/mesh.py` |
| `accessor` / `bufferView` / `buffer` | flattened in exporter | `export/gltf.py` |
| `node` transform / scene graph | implicit (single mesh, world-space verts) | `export/gltf.py` |
| `asset.extras` (provenance) | `asset_meta` dict | `export/gltf.py` |

### 2.2 Conventions that bite on import

- **Units are meters. Y is up. Right-handed.** glTF mandates this. Engines that
  are Z-up (Blender, Unreal) auto-convert on import, but a mismatch between your
  simulation's axis and glTF's Y-up produces sideways trees. Confirm the
  exporter writes Y-up before blaming the engine.
- **The origin should be the root collar**, sitting at `y = 0`, so the asset
  drops onto a ground plane with no manual offset. This is a *pivot* decision —
  cheap to get right at export, expensive to fix per-instance in-engine.
- **`.glb` (binary) over `.gltf`+`.bin`+textures** for shipping: one file, no
  broken relative paths. palubicki already emits binary. Good.

---

## 3. Geometry generation

### 3.1 Branches → swept tubes

`geom/tubes.py::build_bark_primitive` sweeps a ring of `ring_sides` vertices
along each branch chain, duplicating the seam column (`columns = ring_sides + 1`)
so the bark UV does not wrap-tear. Radius comes from the pipe-model field
(see botany §8.3) with a root flare.

The single most important knob here is **`ring_sides`**: it is a direct
poly-budget multiplier on the woodiest part of the tree.

- 3 sides: triangular twigs — acceptable for distant LOD, visibly faceted up close.
- 5–6 sides: the sweet spot for mid branches.
- 8–12 sides: hero trunk only.

A production pipeline varies `ring_sides` by branch radius / Strahler order, not
globally — thick trunk gets 8, terminal twigs get 3. palubicki currently uses a
single value; **radius-adaptive `ring_sides` is the cheapest available poly
saving** and is listed in the gap matrix.

### 3.2 Leaves → cards (textured quads)

`geom/leaves.py::build_leaves_primitive` places foliage; `leaf_blade.py::build_blade`
builds the actual quad geometry. Each leaf is a small alpha-masked card, with
`cluster_count`, `aspect`, `splay_deg`, and `foliage_depth` controlling how cards
fan out per site. Leaf edge length is scaled by local light
(`compute_effective_leaf_size`, sun/shade `k`) so the `.glb` matches the
simulation's light field — note this couples render output to the FSPM, which is
correct and worth preserving.

Cards are the right call. A geometrically-modeled leaf blade is 20–200×
the triangles of a card for no silhouette gain at normal viewing distance. The
realism lives in the **texture and the translucency**, not the mesh — §4, §5.

### 3.3 Vertex budget intuition

Order-of-magnitude targets (one tree, all LODs aside):

| Use case | Triangles |
|---|---|
| Background game tree (LOD2+) | 500 – 3 k |
| Mid game tree | 5 k – 30 k |
| Hero game tree (LOD0) | 50 k – 200 k |
| Archviz / offline | 200 k – several M |

If a palubicki export blows past these, the cause is almost always (a) too many
`ring_sides`, or (b) one card *per* leaf where one card per *cluster* would do.
Measure before optimizing: dump primitive/triangle counts at export time.

---

## 4. Materials & textures

### 4.1 What palubicki emits today

`export/gltf.py::_convert_material` writes PBR metallic-roughness:
`baseColorFactor`, `metallicFactor`, `roughnessFactor`, an optional
**base-color texture only**, `alphaMode` (`OPAQUE`/`MASK`/`BLEND`),
`alphaCutoff` (for `MASK`), and `doubleSided`. Per-vertex color (`COLOR_0`) is
supported and, when present, the base-color factor is neutralized to white so
vertex color drives the look. Procedural textures are generated in
`geom/_textures.py` (`oak_bark`, `pine_bark`, `birch_bark`, `oak_leaf`,
`pine_needle`, `birch_leaf`) — solid for a PoC, alpha-masked for leaves.

### 4.2 What is missing, in priority order

PBR base color alone reads as flat. The high-leverage additions, each a standard
glTF channel `pygltflib` already supports:

1. **Normal maps (`normalTexture`).** The single biggest realism-per-byte win.
   Bark gets depth without geometry; leaves get vein relief. Procedural bark in
   `_textures.py` can emit a companion normal map from the same height field
   essentially for free. **Prerequisite:** export an explicit `TANGENT`
   attribute (§0) — without it, mirrored UV islands seam and lighting is wrong.
   It is nearly free for tubes (frame already computed at `geom/tubes.py:249-259`)
   but is not emitted today.
2. **Occlusion-Roughness-Metallic (`occlusionTexture` + metallic-roughness
   texture, the "ORM" packing).** Roughness variation (wet vs dry bark, waxy vs
   matte leaf) is what stops a surface looking like plastic.
3. **Emissive** — minor for plants; skip unless doing autumn glow / bioluminescence.

### 4.3 Color management

Author **base color in sRGB**, but **normal / ORM maps in linear** — glTF
requires this split and engines assume it. A normal map accidentally tagged sRGB
produces subtly wrong lighting that is maddening to diagnose. Bake this into the
exporter's texture tagging, not into artist discipline.

---

## 5. The hard problem: foliage rendering

Everything that makes tree rendering uniquely hard lives here.

### 5.1 Alpha: mask vs blend

- **`MASK`** (alpha test, `alphaCutoff`) — binary cutout. **Order-independent**,
  cheap, no sorting. Correct default for dense foliage and what palubicki uses.
- **`BLEND`** (alpha blend) — smooth edges but **draw-order dependent**: leaves
  drawn out of order show halos and pop. Reserve for soft edges only, and expect
  sorting pain.

Standard production trick: **`MASK` for the body of the canopy, a thin `BLEND`
fringe** only where soft silhouette matters. Also: alpha-tested foliage benefits
enormously from **alpha-to-coverage / MSAA** in-engine, and from authoring a
**dilated (alpha-bleed) texture** so mip-mapping doesn't erode thin leaves into
nothing at distance — a classic, invisible-until-you-know-it bug.

### 5.2 Translucency — the missing ingredient

A real leaf is **backlit**: light passes *through* it. PBR metallic-roughness
opaque shading cannot express this, and its absence is the #1 reason procedural
foliage reads as "fake." The fixes, in glTF terms:

- **`KHR_materials_transmission` / `KHR_materials_diffuse_transmission`** — the
  standard extensions for thin-surface light transport. `diffuse_transmission`
  is the right *physics* for leaves — but see §0: it is still a Release Candidate
  and unsupported in all four target engines as of 2026, so it cannot be the
  default. Emit it as forward-looking metadata; drive the actual backlight from a
  thickness mask + per-engine subsurface shader.
- Failing extension support, engines expose a **two-sided / subsurface foliage
  shader** (Unreal's *Two Sided Foliage* model, Unity's *Translucency*) — you
  export an opaque double-sided card plus a **thickness/transmission map** and
  wire it up in-engine.

palubicki emits neither extension today. This is the highest-value foliage
upgrade after normal maps. (Gap matrix, §12.)

### 5.3 Texture atlasing

All leaf variants for a species should live in **one atlas** so the whole canopy
is **one material = one draw call**. palubicki's per-species procedural leaf PNGs
are already close; the step is to pack variants (age, sun/shade tint, a few
shapes) into a single sheet and offset UVs per card. Fewer materials is often a
bigger win than fewer triangles.

---

## 6. Bark surface

Bark is where normal/height maps earn their keep (botany §8.4 catalogues the
species patterns: smooth, plated, fissured, shaggy, peeling). Practical notes:

- **Tiling + a low-frequency variation mask** beats one giant unique texture:
  tile a detail bark normal, break repetition with a large-scale color/roughness
  overlay.
- **UV seam** — the duplicated seam column in `tubes.py` already gives clean
  wrap; keep vertical UV proportional to branch length so bark doesn't stretch on
  long internodes.
- **Triplanar projection** is the robust fallback for the root flare and forks
  where tube UVs distort; worth it on the trunk only.

---

## 7. Performance: instancing, LOD, impostors

This is the section that turns "a tree" into "a forest."

### 7.1 Instancing

A forest is the same handful of tree assets drawn thousands of times.
**`EXT_mesh_gpu_instancing`** is the glTF extension for this; engines also do it
natively (Unreal HISM/Nanite foliage, Unity GPU instancing). palubicki exports
one mesh with world-space baked vertices — fine for a single hero tree, but it
means **no instancing reuse**. For forest export, emit a tree at the origin and a
**node transform per placement** instead of baking positions. (Gap matrix.)

### 7.2 Level of detail (LOD)

**`MSFT_lod`** is the glTF extension carrying discrete LOD chains — but it is a
**dead vendor extension** ignored by three.js, Blender, Unreal and Unity (§0).
Treat it as **web-viewer-only** wiring; game engines build LOD groups natively
from the same tiers, and the full master is left intact for Nanite. A tree needs
at least three tiers regardless of how they're wired:

- **LOD0** full tubes + cards (hero, near).
- **LOD1** reduced `ring_sides`, clustered cards, atlased.
- **LOD2** a handful of cross-quads or a single impostor.

The graph makes LOD generation natural: prune by Strahler order for branches,
merge cards by cluster for leaves. palubicki generates a single LOD today.

### 7.3 Impostors / billboards

At distance, the cheapest correct tree is **not geometry at all** — it is an
**hemi-octahedral impostor** (a small atlas rendered from ~12–16 angles above
the horizon — hemi, not full-octahedral, since trees are never seen from below;
displayed on a camera-facing card with normal + depth so it still lights and
parallaxes correctly). This is how every open-world game renders distant
forests. **Caveat (§0):** the current offline rasterizer (`render/renderer.py`)
is matplotlib — screen-space only, it *cannot* bake multi-angle offscreen.
Impostor baking requires a headless GL backend (moderngl/pyrender), which is the
single biggest infra dependency and is deferred to last.

---

## 8. Compression & transport

For web/game delivery, raw `.glb` is large. Two standard, engine-supported
compressions:

- **Geometry: Draco or `EXT_meshopt_compression`.** meshopt is generally the
  better runtime choice (fast decode, also compresses animation). 5–10× on vertex
  data.
- **Textures: `KHR_texture_basisu` (KTX2 / Basis Universal).** GPU-native
  compressed textures that stay compressed *in VRAM* — not just smaller on disk
  but smaller in memory, which is the real constraint for a foliage atlas.

palubicki ships uncompressed PNG + uncompressed buffers — correct for a PoC and a
debuggable editor, wrong for shipping. Add as an export flag, not a default.

---

## 9. Animation: wind

Static trees read as dead. Wind is expected. glTF supports two mechanisms:

1. **Vertex animation via a skeleton (skin + joints).** Paint branch hierarchies
   as a bone chain; engines sway the skeleton. Heavy, most controllable.
2. **Shader-driven wind from vertex attributes.** The dominant game approach:
   bake per-vertex data into **standard `COLOR_n`/`TEXCOORD_n` channels — never
   `_underscore` custom attributes**, which three.js and Unity silently drop on
   import (§0). Concretely: `COLOR_0=(phase, stiffness, leafMask)` (float) +
   `TEXCOORD_1=branch pivot`, and let an engine wind shader (SpeedTree-style,
   Unreal's *SimpleGrassWind* / *Pivot Painter*) deform at runtime. No skeleton,
   scales to thousands of instances. (Unity keeps the channel only if the
   material declares it.)

The FSPM graph is ideally placed to author approach (2): pivot = parent node
position, stiffness ∝ pipe-model radius, phase from branch index. palubicki
exports none of this yet; per-vertex wind attributes are the natural bridge
because the graph already knows the hierarchy a wind shader needs.

---

## 10. Validation

Treat the asset as something to *verify*, not assume (cf. the project's
verification discipline):

- **glTF-Validator** (Khronos) in CI on every export — catches accessor/bounds/
  spec errors before an engine does.
- **three.js viewer round-trip** — the editor (`edit/static/app.js`) is already a
  live validator; confirm alpha, double-sidedness, and Y-up there first.
- **Engine round-trip** — import into Blender (the reference glTF importer) and
  one target engine; check scale (meters), pivot (root at origin), and that
  foliage materials survive.
- **Triangle / material / draw-call counts** logged at export — a regression here
  is a performance regression even when the picture looks identical.

---

## 11. From graph to asset: the pipeline in one view

```text
FSPM tree-graph  (sim/tree.py — nodes, internodes, pipe radii, light_factor)
        │
        ▼  geometry generation
 tubes.py  (bark, ring_sides)      leaves.py + leaf_blade.py  (cards, clusters)
        │                                  │
        ▼  materials + textures            ▼
 _textures.py  (procedural bark / leaf PNGs, alpha masks)
        │
        ▼  Mesh{ Primitive[], Material }   (geom/mesh.py)
        │
        ▼  export
 export/gltf.py  (write_glb_to_bytes — PBR metallic-roughness, .glb)
        │
        ├──▶ edit/static  (three.js GLTFLoader — live viewer)
        └──▶ engine import (Blender / Unreal / Unity — archviz / games)
```

---

## 12. Gap matrix: what palubicki has vs. needs

| Capability | Status | Where / how to add | glTF mechanism |
|---|---|---|---|
| glTF 2.0 `.glb` export | ✅ have | `export/gltf.py` | core |
| PBR metallic-roughness | ✅ have | `_convert_material` | core |
| Base-color texture (procedural) | ✅ have | `_textures.py` | core |
| Alpha `MASK`/`BLEND` + cutoff, double-sided | ✅ have | `Material` | core |
| Per-vertex color | ✅ have | `Primitive.colors` | `COLOR_0` |
| **Normal maps** | ❌ gap | emit from bark height field in `_textures.py` | `normalTexture` |
| **Roughness/ORM maps** | ❌ gap | pack + tag linear | metallic-roughness texture |
| **Leaf translucency / SSS** | ❌ gap | foliage backlight | `KHR_materials_diffuse_transmission` |
| **Texture atlasing** (1 draw call/species) | ⚠ partial | pack leaf variants, offset UVs | core |
| **Radius-adaptive `ring_sides`** | ❌ gap | vary by Strahler/radius in `tubes.py` | core |
| **LOD chain** | ❌ gap | prune branches / merge cards | `MSFT_lod` |
| **Impostors / billboards** | ❌ gap | atlas from `render/renderer.py` | card + atlas |
| **GPU instancing (forests)** | ❌ gap | export node transforms, not baked verts | `EXT_mesh_gpu_instancing` |
| **Geometry compression** | ❌ gap | export flag | `EXT_meshopt_compression` |
| **Texture compression** | ❌ gap | export flag | `KHR_texture_basisu` (KTX2) |
| **Wind authoring data** | ❌ gap | bake pivot/stiffness/phase to attributes | `COLOR_0` / custom attribute |

**Recommended order of work** — *superseded by the 2026 plan (§0)*. The original
look-first order was: normal maps → leaf translucency → roughness/ORM →
atlasing → `ring_sides` → LOD → wind → instancing → compression. The reconciled
plan in [`export-pipeline-design.md`](./export-pipeline-design.md) instead does
**forest instancing first** (P0, highest ROI, independent of texture work), then
**wind** (P1 — its `TANGENT` emission unblocks normal maps), then the
**photoreal master** (P2: geometric leaf blade + normal/ORM + color management),
then profiles+validation (P3), LOD+impostor (P4), and hero skinned wind (P5).

---

## 13. References

**Format & extensions**
- glTF 2.0 specification, Khronos — https://registry.khronos.org/glTF/
- glTF extension registry (KHR_/EXT_/MSFT_) — `KHR_materials_diffuse_transmission`,
  `KHR_texture_basisu`, `EXT_meshopt_compression`, `EXT_mesh_gpu_instancing`,
  `MSFT_lod`.
- glTF-Validator — https://github.com/KhronosGroup/glTF-Validator

**Foliage & vegetation rendering**
- SpeedTree — the reference vegetation pipeline; wind model and LOD/impostor
  conventions are de-facto standards.
- Weber, J. & Penn, J. (1995) "Creation and Rendering of Realistic Trees,"
  *SIGGRAPH '95* — the model behind Blender's Sapling and much of SpeedTree.
- Octahedral impostors — Brian Karis / "Imposters" technique writeups; Unreal
  Engine impostor baker docs.
- Pivot Painter (Unreal) — baking hierarchy/pivot data into vertices for wind.

**PBR & color**
- *Physically Based Rendering* (Pharr, Jakob, Humphreys) — the reference text.
- Khronos PBR / glTF sample renderer — canonical metallic-roughness behavior.

**Project cross-reference**
- [botany/plant-structure.md](./botany/plant-structure.md) — the data-structure /
  morphology layer this document projects into geometry.
