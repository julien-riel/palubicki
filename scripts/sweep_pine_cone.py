"""Pine emergent-cone calibration sweep (#96).

Pine under shadow_propagation + generous bounds builds a HUGE active-bud cloud
(k=5 whorls): ~72k buds at 8 yr, runaway (38 min / 9 GB) at 30 yr. Dormant buds
are never removed, so cost is O(total buds)/iteration. Calibration must keep the
pool bounded (dormancy / shade mortality / selective persistence) AND earn a
cone. banked_vigor scale is large (q90~21, max~4k), so establish_threshold must
be ~10-50, not fir's 0.5.

Runs combos in a multiprocessing.Pool (NOT workflow agents — 180 s watchdog),
pine-only.

    .venv/bin/python scripts/sweep_pine_cone.py grid <years>     # the GRID below, seed 0
    .venv/bin/python scripts/sweep_pine_cone.py verify <pr> <rel> <est> <pipe> <vd> <years>
"""
from __future__ import annotations

import sys
import time
from multiprocessing import Pool
from pathlib import Path

from palubicki.config import load_config
from palubicki.sim.diagnostics import compute_metrics
from palubicki.sim.simulator import simulate

# Generous NON-cone bounds: the cone must emerge, not be prescribed. rx/rz a hair
# tighter than the cone preset's 4.4 to curb the bud cloud without shaping form.
_SHADOW = {
    "exposure": "shadow_propagation",
    "envelope.shape": "half_ellipsoid",
    "envelope.rx": 4.4, "envelope.ry": 20.0, "envelope.rz": 4.4,
    "shadow.enabled": True, "shadow.measure": "skyview",
}

_OUT = Path("out")

# Pool-bounding is on for all (mortality + q_dormancy). Grid (seed 0):
# (persist_rate_fraction, release_years, establish_threshold, pipe_exponent,
#  q_dormancy, mort_light_threshold).
_GRID = [
    (0.40, 6.0, 25.0, 2.90, 0.3, 0.50),
    (0.40, 6.0, 25.0, 3.60, 0.3, 0.50),   # thinner trunk
    (0.40, 6.0, 25.0, 4.00, 0.3, 0.50),   # thinnest trunk (pipe capped at 4.0)
    (0.40, 6.0, 25.0, 4.00, 0.5, 0.50),   # smaller pool (higher q_dormancy)
    (0.50, 6.0, 25.0, 4.00, 0.3, 0.50),   # widest crown
    (0.50, 6.0, 25.0, 4.00, 0.4, 0.50),
]


def _run(args):
    pr, rel, est, pipe, qd, mlt, seed, years = args
    ov = {
        "seed": seed, "sim.max_simulation_years": years,
        "sim.length_banking.enabled": True,
        "sim.length_banking.persist_rate_fraction": pr,
        "sim.length_banking.release_years": rel,
        "sim.length_banking.establish_threshold": est,
        "geom.pipe_exponent": pipe,
        "shadow.q_dormancy": qd,
        "shadow.mortality_enabled": True,
        "sim.shade_mortality.light_threshold": mlt,
    }
    ov.update(_SHADOW)
    _OUT.mkdir(exist_ok=True)
    t0 = time.time()
    cfg = load_config(yaml_path=None, cli_overrides=ov,
                      output=(_OUT / f"pine_pr{pr}_pipe{pipe}_q{qd}_s{seed}.glb"), species="pine")
    tree = simulate(cfg)
    m = compute_metrics(tree, cfg=cfg)
    dt = time.time() - t0
    return {
        "pr": pr, "rel": rel, "est": est, "pipe": pipe, "qd": qd, "mlt": mlt,
        "seed": seed, "years": years, "n": len(tree.all_internodes),
        "mono": m["crown_monotonicity"], "h": m["tree_height"],
        "cr": m["crown_radius"], "trunk": m["trunk_base_diameter"],
        "cont": m["main_axis_continuation_rate"], "dev": m["leader_deviation_deg"],
        "dt": dt,
    }


def _fmt(r):
    return (f"pr={r['pr']:.2f} rel={r['rel']:.0f} est={r['est']:.0f} pipe={r['pipe']:.2f} "
            f"qd={r['qd']:.1f} s{r['seed']} y{r['years']} | mono={r['mono']:+.3f} "
            f"h={r['h']:.2f} cr={r['cr']:.2f} trunk={r['trunk']:.3f} cont={r['cont']:.2f} "
            f"dev={r['dev']:.1f} | n={r['n']} {r['dt']:.0f}s")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "grid"
    if mode == "grid":
        years = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        combos = [(*g, 0, years) for g in _GRID]
        with Pool(processes=min(len(combos), 6)) as pool:
            for r in pool.imap_unordered(_run, combos):
                print(_fmt(r), flush=True)
        return
    if mode == "pick":
        # y30 single-seed shortlist to pick the final config (crown/height grow by y30).
        years = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        shortlist = [
            (0.50, 6.0, 25.0, 4.00, 0.5, 0.50, 0, years),  # wide crown, fast pool
            (0.40, 6.0, 25.0, 4.00, 0.5, 0.50, 0, years),  # fastest, safest trunk
            (0.50, 6.0, 25.0, 4.00, 0.4, 0.50, 0, years),  # widest crown, mid pool
        ]
        with Pool(processes=3) as pool:
            for r in pool.imap_unordered(_run, shortlist):
                print(_fmt(r), flush=True)
        return
    if mode == "verify":
        pr, rel, est, pipe, qd, mlt = (float(sys.argv[i]) for i in range(2, 8))
        years = int(sys.argv[8]) if len(sys.argv) > 8 else 30
        combos = [(pr, rel, est, pipe, qd, mlt, s, years) for s in (0, 1, 2)]
        rows = []
        with Pool(processes=3) as pool:
            for r in pool.imap_unordered(_run, combos):
                print(_fmt(r), flush=True)
                rows.append(r)
        n = len(rows)
        print("MEAN | mono={:+.3f} h={:.2f} cr={:.2f} trunk={:.3f}".format(
            sum(x["mono"] for x in rows) / n, sum(x["h"] for x in rows) / n,
            sum(x["cr"] for x in rows) / n, sum(x["trunk"] for x in rows) / n), flush=True)
        return
    raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
