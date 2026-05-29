# Root flare at trunk base — design (issue #8)

## Goal

Add a visible flare at the base of the trunk where it meets the ground. Real
trees show a "root collar" zone — the trunk widens over the bottom ~10% of its
height, sometimes with sinusoidal buttress ridges (oak, beech, fig). Today the
trunk meets a flat fan cap (`_emit_root_cap` in `geom/tubes.py`) with no flare,
so the base looks like a cylinder dropped onto a plane.

This is a **render-time visual expansion only**. The simulation
`Internode.diameter` never changes; sag, structure, light, shedding, and the
diagnostic harness all keep their original values.

## Scope

Full scope of #8 in one PR:

1. Axisymmetric radial flare (MVP).
2. Azimuthal buttress undulation (nice-to-have).
3. Per-tree RNG variation (nice-to-have).

Out of scope (unchanged from issue): true below-soil root architecture,
tropical buttresses / prop roots / aerial roots, and any modification to
`Internode.diameter`.

## Config — `GeomConfig` additions

Five new fields in `src/palubicki/config.py`, each with `ui` metadata:

```python
root_flare_height: float = 0.3       # meters above base, over which the flare blends in
root_flare_factor: float = 1.6       # radius multiplier at the very base (1.0 = off)
root_flare_falloff: Literal["linear", "smoothstep"] = "linear"
root_buttress_count: int = 0         # 0 = smooth; 3–6 for ridged species
root_buttress_amplitude: float = 0.15
root_flare_variation: float = 0.08   # per-tree ± fractional jitter on factor (0 = identical flares)
```

Validation (in the existing `validate`/`ConfigError` path in `config.py`):

- `root_flare_factor >= 1.0`
- `root_flare_height >= 0`
- `root_buttress_count >= 0`
- `0 <= root_buttress_amplitude < 1`
- `0 <= root_flare_variation < 1`

The generic default `root_flare_factor = 1.6` means **every** tree flares by
default. `root_flare_factor = 1.0` reproduces the current cylinder-meets-fan
appearance exactly (acceptance criterion).

## Geometry — the math

Let `base_y = chains[0].nodes[0].position[1]` (trunk root ground reference) and,
for a trunk node at height `y`:

```
t        = clamp((height - (y - base_y)) / height, 0, 1)   # 1 at base, 0 at top of flare zone
falloff  = t                  (linear)
         | t*t*(3 - 2*t)      (smoothstep)
flare(y) = 1 + (factor - 1) * falloff
butt(y,θ)= 1 + amplitude * falloff * cos(count*θ + phase)
```

The buttress amplitude rides the **same** `falloff` as the radial flare, so
ridges live only inside the collar and vanish at the top of the flare zone.

Effective per-vertex radius for the trunk chain:

```
r_eff[i, k] = radii[i] * flare(y_i) * butt(y_i, θ_k)
```

### Where it lives — `_emit_chain_tube`

Today the effective radius is `radii_arr` of shape `(N,)`, broadcast as
`radii_arr[:, None, None]` against the `(N, columns, 3)` radials. Buttress is
azimuthal, so it cannot be a per-node radius — it needs a per-column field.

`_emit_chain_tube` gains an optional `flare` descriptor argument:

- `flare is None` (every non-trunk chain): unchanged `(N,)` fast path.
- `flare` present (trunk only): build `r_eff` of shape `(N, columns)` and use
  `r_eff[:, :, None]` in the position expansion.

The buttress angle uses the **same** `angles` array the ring already computes
(`k % ring_sides`), so `angles[ring_sides] == angles[0]` and the UV seam stays
bit-welded. Normals stay radial (`normals = radials`), consistent with how the
existing code already ignores taper-induced normal tilt along the tube.

Only `chains[0]` (the trunk) receives the descriptor; all other chains pass
`flare=None`.

### `_emit_root_cap`

Unchanged. It reuses ring-0 positions, which are now inflated upstream, and the
center vertex stays at the base. No edits needed.

### Sim layer

Untouched. `build_bark_primitive` reads `Internode.diameter` exactly as before;
the flare multiplies the *rendered* radius only. The diagnostic harness (#1)
reports the same trunk base diameter as before.

## Per-tree variation

`build_bark_primitive` derives `rng = np.random.default_rng(cfg.seed)`
(threaded from `builder.py` via `cfg.seed`). It uses `rng` for:

1. A buttress **phase** offset in `[0, 2π)` — rotates ridges per tree.
2. A `±root_flare_variation` fractional jitter on `root_flare_factor` — so even
   smooth-flared species (`count == 0`) differ across a forest. The applied
   factor is `factor * (1 + rng.uniform(-v, v))` (clamped to `>= 1.0`), where
   `v = root_flare_variation`. Setting `v = 0` makes every tree's flare
   identical (useful for deterministic comparisons).

`cfg.seed` is already per-tree in forests (`write_glb_forest` builds each tree
with its own `per_tree_cfg`), so variation falls out naturally.

## Per-species YAML defaults

| species | factor | height | falloff    | buttress_count | amplitude |
|---------|--------|--------|------------|----------------|-----------|
| oak     | 1.8    | 0.4    | smoothstep | 5              | 0.15      |
| maple   | 1.6    | 0.3    | linear     | 3              | 0.10      |
| pine    | 1.3    | 0.2    | linear     | 0              | —         |
| fir     | 1.3    | 0.2    | linear     | 0              | —         |
| birch   | 1.15   | 0.15   | linear     | 0              | —         |
| default | 1.6    | 0.3    | linear     | 0              | 0.15      |

All species inherit the default `root_flare_variation = 0.08`; no species YAML
overrides it unless we find one that needs flatter or more varied flares.

## Tests

- **Unit (`tests/geom/`)**:
  - `root_flare_factor=1.0` ⇒ trunk positions bit-identical to a no-flare build
    (acceptance criterion).
  - linear vs smoothstep scaling matches the closed form at a known `y`.
  - buttress modulation present iff `root_buttress_count > 0`.
  - seam vertex welded: column 0 == column `ring_sides` at the base ring.
- **Goldens**: regenerate species goldens (`test_species_goldens.py`) and the
  ellipsoid goldens (`test_goldens.py`, which use `GeomConfig()` default 1.6),
  then review the `.glb` visually before committing.

## Acceptance criteria (from #8)

- [ ] `palubicki generate --species oak --seed 0` produces a visibly flared base.
- [ ] `root_flare_factor=1.0` reproduces the current cylinder-meets-fan look.
- [ ] No change to `sim/`; diagnostic harness reports the same trunk base diameter.
- [ ] Trunk goldens regenerated and reviewed in the same PR.
