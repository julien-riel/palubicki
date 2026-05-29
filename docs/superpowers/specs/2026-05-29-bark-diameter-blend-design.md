# Bark variation blended by `Internode.diameter` (three-way tint)

**Issue:** #9 — `render: bark variation blended by Internode.diameter (smooth at tips, cracked at trunk)`
**Date:** 2026-05-29
**Status:** Approved (brainstorm), pending implementation plan

## Goal

Vary bark appearance along the trunk by `Internode.diameter`: pale/young bark on
thin twigs, mature bark mid-trunk, dark/senescent bark at the thick base. Today
every internode of a tree uses one flat bark color, so a 30-year-old oak shows
identical bark on a 2 cm twig and a 30 cm trunk. This is a render-time blend — no
sim change. `Internode.diameter` is the only blend driver.

The issue lists a two-way blend (young → mature) as MVP and a three-way blend
(young → mature → senescent) as nice-to-have. **We implement the three-way blend
directly** — it generalizes the two-way (leave the senescent tint unset to get
two-way) and is the explicitly requested scope.

## Key constraint that shapes the design

The internal renderer (`render/renderer.py:_flatten`) shades each primitive with
one **flat `material.base_color`** and ignores textures and UVs entirely.
Procedural bark *textures* therefore only ever appear in exported GLB viewed in
an external viewer — never in palubicki's own PNG renders or the golden tests.

Consequence: the variation that actually reaches the screen in **both** render
paths is the **tint color**, not the texture pattern. glTF can bind only one bark
texture per primitive, and `COLOR_0` multiplies that single texture — blending
three texture *patterns* would require a custom shader extension (rejected, out
of scope). So the design carries the young→mature→senescent variation as a
per-vertex color tint over the species' existing single bark texture.

## Chosen approach: tint-only, three-stop gradient

Rejected alternatives:

- **B — three procedural texture variants bound per chain:** coarse, blocky seams
  where a chain switches texture, still no smooth pattern blend. Not worth it.
- **C — true multi-texture shader blend (`KHR_*` extension):** real pattern blend
  in glTF only — *still invisible in the internal renderer/goldens* — large,
  glTF-bound. This is the documented LATER upgrade path if tint proves
  insufficient, matching the issue's "revisit if washed-out."

Approach A is the only option fully visible in both render paths, seam-free, and
matching the issue's "MVP picks option 1 (per-vertex tint)."

## Components

### 1. Blend math — `bark_tint` helper

New pure, vectorized helper (in `geom/_textures.py` or a small `geom/bark_blend.py`):

```python
def bark_tint(diameter: np.ndarray, stops: BarkBlendStops) -> np.ndarray:
    """Map per-vertex diameter to RGB tint via a 3-stop piecewise-linear gradient.
    Returns (N, 3) float32."""
```

Stops: `(d_young, d_mature, d_senescent)` diameters and `(c_young, c_mature,
c_senescent)` RGB colors. Mapping:

- `d <= d_young`                  → `c_young`
- `d_young  < d <= d_mature`      → lerp `c_young → c_mature`
- `d_mature < d <= d_senescent`   → lerp `c_mature → c_senescent`
- `d >= d_senescent`              → `c_senescent`

Clamped at both ends; defined and continuous at the stop boundaries. Requires
`d_young <= d_mature <= d_senescent` (validated; degenerate equal stops collapse
the corresponding segment without dividing by zero).

### 2. Geometry — per-vertex colors

`Primitive` (`geom/mesh.py`) gains `colors: np.ndarray | None` — `(V, 3)` float32,
`None` when no blend.

In `geom/tubes.py`, `build_bark_primitive` / `_emit_chain_tube`:

- Each ring corresponds to one chain node; its diameter is `2 * chain.radii[node]`
  (already available). Run `bark_tint` per node and broadcast the resulting RGB
  across the ring's `columns` vertices.
- Root-cap center vertex (`_emit_root_cap`) uses the base node's diameter (the
  senescent end).
- When blend is disabled, emit `colors=None` and the geometry is identical to
  today.

`build_bark_primitive` takes the blend stops (or `None`) as a parameter, passed
through from `builder.py`.

### 3. Internal renderer

`render/renderer.py:_flatten`: when a primitive has `colors`, the per-face color
is the **mean of that triangle's three vertex colors** (replacing `base_color`
for that primitive). When `colors is None`, unchanged (`base_color` broadcast).
`_shade` is unchanged — Lambert factor still applies on top.

### 4. glTF export

`export/gltf.py` (both `write_glb_to_bytes` and `write_glb_forest`): when a
primitive has `colors`, emit a `COLOR_0` accessor (`VEC3` float, `with_minmax=False`)
and add `COLOR_0` to the primitive's `Attributes`. For a bark material whose
primitive carries colors, set `baseColorFactor = (1, 1, 1, 1)` so the final color
is `COLOR_0 × texture` — the tint carries the albedo, consistent with the internal
renderer (which has no texture, so shows the tint directly).

When a primitive has no colors, the existing path is **byte-for-byte unchanged**
(satisfies acceptance criterion: blend off ⇒ identical to today).

### 5. Config — `GeomConfig`

Presence-gated, mirroring the issue's `*_young is None ⇒ no blend`:

```python
bark_tint_young:      tuple[float, float, float] | None = None  # gate: None ⇒ blend off
bark_tint_mature:     tuple[float, float, float] | None = None  # None ⇒ falls back to bark_color
bark_tint_senescent:  tuple[float, float, float] | None = None
bark_blend_diameter_young:     float = 0.02
bark_blend_diameter_mature:    float = 0.10
bark_blend_diameter_senescent: float = 0.30
```

Blend is active iff `bark_tint_young is not None`. `bark_tint_mature` defaults to
`bark_color` when unset (so the mid look matches today). `bark_tint_senescent`
unset ⇒ two-way blend (young → mature only, clamped above `d_mature`).

`builder.py` assembles a `BarkBlendStops | None` from the config and passes it to
`build_bark_primitive`.

### 6. Per-species defaults — on by default

Hand-tuned tints + stops in all five `configs/species/*.yaml` (oak, pine, birch,
maple, fir), with the blend **enabled by default** so it is visibly on. Mature
tint set to each species' current `bark_color` to preserve the mid-trunk look.
Indicative values (tunable):

| species | young            | mature (= today)   | senescent          | stops (y / m / s, m) |
|---------|------------------|--------------------|--------------------|----------------------|
| oak     | (0.45,0.38,0.30) | (0.35,0.22,0.12)   | (0.22,0.20,0.16)   | 0.02 / 0.10 / 0.30   |
| birch   | paper-white      | mid                | dark fissured      | 0.02 / 0.10 / 0.30   |
| pine    | ochre-pale       | ochre/red          | grey-brown         | 0.02 / 0.10 / 0.30   |
| maple   | grey-green       | grey-brown         | dark furrowed      | 0.02 / 0.10 / 0.30   |
| fir     | grey-pale        | grey-brown         | dark               | 0.02 / 0.10 / 0.30   |

Exact RGB triples finalized during implementation against rendered output.

## Data flow

```
species.yaml (tints + stops)
  → GeomConfig
  → builder.py assembles BarkBlendStops | None
  → build_bark_primitive(..., stops)
      → per node: diameter = 2*radii → bark_tint → broadcast to ring columns
      → Primitive.colors (V,3) | None
  → renderer._flatten: face color = mean(vertex colors)  [internal PNG / goldens]
  → gltf: COLOR_0 accessor + baseColorFactor=white       [external GLB viewers]
```

## Testing

- **Unit** (`bark_tint`): end clamping (below `d_young` → `c_young`, above
  `d_senescent` → `c_senescent`), exact stop values at boundaries, midpoint lerp,
  monotonic interpolation, degenerate equal-stops safety, vectorized shape.
- **Geometry**: `build_bark_primitive` emits `colors` of shape `(V,3)` when stops
  given, `None` when not; thin-ring color ≈ young, thick-ring color ≈ senescent.
- **glTF**: `COLOR_0` present and `baseColorFactor == [1,1,1,1]` when colors set;
  blend-off export is byte-identical to a pre-change baseline GLB.
- **Goldens**: regenerate the five-species golden PNGs (precedent: root-flare
  golden regen, commit c73a81a). Twigs visibly paler, base visibly darker.
- **Smoke**: `palubicki generate` succeeds for all five species.

## Acceptance criteria (from issue)

- [ ] `bark_tint_young` not set → identical output to today (byte-identical GLB,
      unchanged goldens for that config).
- [ ] `bark_tint_young` set on oak → twigs (< 2 cm) visibly young tint; trunk base
      (> ~15 cm, here ≥ `d_senescent` = 30 cm) visibly senescent tint.
- [ ] No regression in `palubicki generate` smoke tests for all species.
- [ ] `Internode.diameter` is the only blend driver — no new sim concept.

## Out of scope

- Vertical-axis (height) modulation of bark.
- True texture-pattern blending (approaches B/C) — LATER upgrade path.
- 3D bark relief / displacement, annual rings, bark shedding, lichen/moss overlay.
- Replacing the procedural texture system with image textures.
- Deriving blend ranges from the tree's diameter distribution (percentiles) —
  stops are hand-tuned per species.
