# palubicki

Self-organizing 3D tree generator based on Palubicki, Horel, Longay, Runions, Lane, Měch, Prusinkiewicz — *Self-organizing tree models for image synthesis*, SIGGRAPH 2009.

V1 implements the BHse model: marker points distributed in a parametric envelope drive bud competition for space; Borchert-Honda allocation routes resources from the root to the buds; tropisms (gravity, photo direction, inertia) bias growth; low-quality branches are shed. Output is a `.glb` (glTF 2.0 binary) usable in any standard viewer.

## Install

```bash
pip install -e ".[dev]"
```

## Usage

```bash
# Bushy ellipsoid tree (oak-like)
palubicki generate -o oak.glb \
  --envelope half_ellipsoid --envelope-radii 4 6 4 \
  --seed 42

# Conifer
palubicki generate -o pine.glb \
  --envelope cone --envelope-radii 2 8 2 \
  --w-gravity 0.5

# Dump all defaults to start a config file
palubicki dump-defaults > my-config.yaml
palubicki generate -o tree.glb --config my-config.yaml

# Recover the config used to generate an existing .glb
palubicki dump-config tree.glb > used.yaml
```

## Architecture

- `src/palubicki/sim/` — pure simulation (markers, buds, BH, tropisms, shedding). No geometry, no glTF.
- `src/palubicki/geom/` — skeleton → tessellated tubes (parallel transport frames) + cross-quad leaves. Outputs a neutral `Mesh`.
- `src/palubicki/export/` — `Mesh` → `.glb`. Core glTF 2.0, no extensions, max viewer compatibility.
- `src/palubicki/cli.py` — orchestrates.

## Configuration

All parameters are exposed via YAML. CLI flags expose the most-tweaked ones; the rest are YAML-only. Run `palubicki dump-defaults` for the full schema with defaults.

The effective config (including all overrides) is embedded in `asset.extras.config` of the produced `.glb` for reproducibility.

## Tests

```bash
pytest                  # unit tests (fast)
pytest -m slow          # integration + goldens
pytest --cov            # coverage report
```

## Roadmap

- **V2** : voxel light shadowing (BHls).
- **V3** : obstacles + multi-tree forest simulation.
- **V4** : species presets (apple, oak, pine, willow, birch) reproducing Fig. 12.

See `docs/superpowers/roadmap/`.

## References

Palubicki et al., 2009 — [Self-organizing tree models for image synthesis](https://algorithmicbotany.org/papers/selforg.sig2009.html).
