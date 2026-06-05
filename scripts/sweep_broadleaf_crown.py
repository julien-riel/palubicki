"""Calibration harness for the emergent broadleaf rounded crown (#97).

Runs a species under `exposure: shadow_propagation` with neutral (non-cone)
bounds and the rounded length-banking profile, printing the crown-form
diagnostics (crown_widest_frac, crown_monotonicity, apex_sharpness,
clear_bole_fraction) plus the banded dimensions (height / crown_radius /
trunk_base_diameter) and the leader signals — multi-seed.

Usage:
    .venv/bin/python scripts/sweep_broadleaf_crown.py oak --seeds 0 1 2 \
        --set sim.length_banking.persist_rate_fraction=0.55 \
        --set sim.length_banking.release_years=7
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from palubicki.config import load_config
from palubicki.sim.diagnostics import compute_metrics
from palubicki.sim.simulator import simulate

# Neutral (non-cone) shadow bounds per species. Generous rx/rz so the crown form
# emerges from light competition + age-banking, not the envelope wall.
SHADOW = {
    "oak":   {"envelope.shape": "half_ellipsoid", "envelope.rx": 5.5, "envelope.ry": 15.0, "envelope.rz": 5.5},
    "maple": {"envelope.shape": "half_ellipsoid", "envelope.rx": 5.0, "envelope.ry": 13.0, "envelope.rz": 5.0},
    "ash":   {"envelope.shape": "half_ellipsoid", "envelope.rx": 4.5, "envelope.ry": 14.0, "envelope.rz": 4.5},
    "birch": {"envelope.shape": "half_ellipsoid", "envelope.rx": 5.0, "envelope.ry": 14.0, "envelope.rz": 5.0},
}
# Pyramid (downward self-shadow, no side light) is what rounds the crown: it
# suppresses the lower-interior so the bole clears, where skyview keeps lower-edge
# branches lit (→ a base-wide cone). Shade mortality bounds the pool + clears the
# base; the rounded length hump narrows the apex.
_COMMON_SHADOW = {
    "exposure": "shadow_propagation",
    "shadow.enabled": True,
    "shadow.measure": "pyramid",
    "shadow.mortality_enabled": True,
}

# Per-species rounded-banking calibration. Oak locked (#97). The recipe: rounded
# profile (a multiplicative age hump), establish_threshold ~ the species vigor
# scale (so the never-established interior cloud is culled → pool bounded + base
# cleared), pipe_exponent at the cap (the heavy pool thickens the bole).
_ROUNDED_BASE = {
    "sim.length_banking.release_years": 6.0,
    "sim.length_banking.decline_years": 12.0,
    "sim.length_banking.young_length_floor": 0.65,
    "sim.length_banking.old_length_floor": 0.40,
    "geom.pipe_exponent": 4.0,
}
CAL = {
    "oak":   {**_ROUNDED_BASE, "sim.length_banking.persist_rate_fraction": 0.55,
              "sim.length_banking.establish_threshold": 2.0,
              "shadow.q_dormancy": 0.45, "sim.shade_mortality.light_threshold": 0.55},
    "maple": {**_ROUNDED_BASE, "sim.length_banking.persist_rate_fraction": 0.50,
              "sim.length_banking.establish_threshold": 1.2,
              "shadow.q_dormancy": 0.45, "sim.shade_mortality.light_threshold": 0.55},
    "ash":   {**_ROUNDED_BASE, "sim.length_banking.persist_rate_fraction": 0.50,
              "sim.length_banking.establish_threshold": 1.5,
              "shadow.q_dormancy": 0.45, "sim.shade_mortality.light_threshold": 0.55},
    "birch": {**_ROUNDED_BASE, "sim.length_banking.persist_rate_fraction": 0.50,
              "sim.length_banking.establish_threshold": 4.5,
              "shadow.q_dormancy": 0.45, "sim.shade_mortality.light_threshold": 0.55},
}


def _coerce(v: str):
    if v in ("True", "true"):
        return True
    if v in ("False", "false"):
        return False
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def run(species: str, seed: int, years: int, extra: dict, banking: bool):
    ov = {"seed": seed, "sim.max_simulation_years": years}
    ov.update(_COMMON_SHADOW)
    ov.update(SHADOW[species])
    if banking:
        ov["sim.length_banking.enabled"] = True
        ov["sim.length_banking.profile"] = "rounded"
        ov.update(CAL[species])
    ov.update(extra)
    cfg = load_config(yaml_path=None, cli_overrides=ov,
                      output=Path("/tmp/sweep.glb"), species=species)
    t0 = time.time()
    tree = simulate(cfg)
    dt = time.time() - t0
    m = compute_metrics(tree, cfg=cfg)
    m["_seconds"] = dt
    m["_internodes"] = len(tree.all_internodes)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("species", choices=list(SHADOW))
    ap.add_argument("--seeds", type=int, nargs="+", default=[0])
    ap.add_argument("--years", type=int, default=30)
    ap.add_argument("--off", action="store_true", help="banking off (raw emergent baseline)")
    ap.add_argument("--set", dest="sets", action="append", default=[],
                    help="extra override key=value (repeatable)")
    args = ap.parse_args()

    extra = {}
    for s in args.sets:
        k, v = s.split("=", 1)
        extra[k] = _coerce(v)

    print(f"# {args.species}  years={args.years}  banking={'OFF' if args.off else 'ON'}  extra={extra}")
    hdr = ["seed", "widest", "mono", "apex", "bole", "height", "crown", "trunk",
           "contin", "leaddev", "intern", "sec"]
    print("  ".join(f"{h:>7}" for h in hdr))
    keys = ["crown_widest_frac", "crown_monotonicity", "apex_sharpness", "clear_bole_fraction",
            "tree_height", "crown_radius", "trunk_base_diameter",
            "main_axis_continuation_rate", "leader_deviation_deg"]
    rows = []
    for seed in args.seeds:
        m = run(args.species, seed, args.years, extra, banking=not args.off)
        rows.append(m)
        vals = [seed] + [m[k] for k in keys] + [m["_internodes"], m["_seconds"]]
        print("  ".join(f"{v:7.3f}" if isinstance(v, float) else f"{v:7d}" for v in vals))
    if len(rows) > 1:
        mean = {k: sum(r[k] for r in rows) / len(rows) for k in keys}
        vals = ["mean"] + [mean[k] for k in keys] + ["", ""]
        print("  ".join(f"{v:7.3f}" if isinstance(v, float) else f"{str(v):>7}" for v in vals))


if __name__ == "__main__":
    sys.exit(main())
