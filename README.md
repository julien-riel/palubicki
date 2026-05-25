# palubicki

Self-organizing 3D tree generator (Palubicki et al. 2009 — SIGGRAPH) exporting glTF.

## Install

```bash
pip install -e ".[dev]"
```

## Usage

```bash
palubicki generate -o tree.glb --envelope ellipsoid --envelope-radii 4 6 4 --seed 42
```

See `palubicki generate --help` and `palubicki dump-defaults` for full configuration.
