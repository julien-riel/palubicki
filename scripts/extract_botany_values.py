"""Extract numeric bounds from the cached botany sources into the manifest.

Companion to scripts/fetch_botany_sources.py. Given the downloaded source cache,
each registered extractor pulls a column of observations from a structured
database (CSV) or a PDF table, reduces it to a ``[lo, hi]`` band, and reports it
with provenance (source key + page/locator). With ``--write`` the proposed
bounds are merged into ``ranges`` in literature.yaml; without it the script only
prints what it would write (dry run).

Extraction is the default path; values that resist parsing stay hand-curated in
the manifest. Prefer structured DBs (BAAD / wood-density CSVs) over PDF parsing
where a source offers both.

PDF extractors need the ``botany`` extra:  pip install -e '.[botany]'

Usage:
    .venv/bin/python scripts/fetch_botany_sources.py        # populate the cache
    .venv/bin/python scripts/extract_botany_values.py       # dry run
    .venv/bin/python scripts/extract_botany_values.py --write
    .venv/bin/python scripts/extract_botany_values.py --only wood_density
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import yaml

# ── Pure numeric helpers (unit-tested in tests/test_extract_botany_values.py) ─


def parse_numeric_column(rows: list[dict], column: str) -> list[float]:
    """Pull a column from CSV-style rows, dropping blanks and non-numeric cells."""
    out: list[float] = []
    for row in rows:
        raw = (row.get(column) or "").strip()
        try:
            out.append(float(raw))
        except (TypeError, ValueError):
            continue
    return out


def range_from_values(
    values: list[float], *, lo_pct: float | None = None, hi_pct: float | None = None
) -> tuple[float, float]:
    """Reduce observations to a [lo, hi] bound.

    Default is the full min/max. Pass ``lo_pct``/``hi_pct`` (0-100) to use a
    percentile band instead, which trims outliers without dropping the bulk of
    the distribution.
    """
    if not values:
        raise ValueError("cannot derive a range from zero observations")
    xs = sorted(values)
    if lo_pct is None and hi_pct is None:
        return (xs[0], xs[-1])
    lo = _percentile(xs, lo_pct if lo_pct is not None else 0.0)
    hi = _percentile(xs, hi_pct if hi_pct is not None else 100.0)
    return (lo, hi)


def _percentile(sorted_xs: list[float], pct: float) -> float:
    if len(sorted_xs) == 1:
        return sorted_xs[0]
    rank = (pct / 100.0) * (len(sorted_xs) - 1)
    lo_i = int(rank)
    hi_i = min(lo_i + 1, len(sorted_xs) - 1)
    frac = rank - lo_i
    return sorted_xs[lo_i] * (1 - frac) + sorted_xs[hi_i] * frac


# ── Extractor registry ───────────────────────────────────────────────────────


@dataclass
class Proposal:
    field: str            # MetricRanges path-style field name
    species: str | None   # None => global
    value: tuple[float, float]
    source: str           # manifest source key
    page: str             # human-readable locator


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def load_species_latin() -> dict[str, str]:
    """config name -> latin binomial, from the manifest's species_latin block."""
    text = resources.files("palubicki.configs").joinpath("literature.yaml").read_text()
    return (yaml.safe_load(text) or {}).get("species_latin", {})


def extract_per_species_csv(
    path: Path,
    *,
    latin_col: str,
    value_col: str,
    field: str,
    source: str,
    page: str,
    species_latin: dict[str, str],
    lo_pct: float | None = None,
    hi_pct: float | None = None,
) -> list[Proposal]:
    """One [lo, hi] Proposal per species whose latin name matches rows in `path`.

    Rows are matched case-insensitively on `latin_col == species_latin[name]`.
    Species with no matching/numeric rows are silently absent from the result
    (logged by the caller, not here).
    """
    rows = _read_csv(path)
    proposals: list[Proposal] = []
    for cfg_name, latin in species_latin.items():
        matched = [r for r in rows if (r.get(latin_col) or "").strip().lower() == latin.lower()]
        vals = parse_numeric_column(matched, value_col)
        if not vals:
            continue
        lo, hi = range_from_values(vals, lo_pct=lo_pct, hi_pct=hi_pct)
        proposals.append(
            Proposal(field, cfg_name, (round(lo, 3), round(hi, 3)), source, page)
        )
    return proposals


def _extract_wood_density(cache: Path) -> list[Proposal]:
    """Per-species wood-density bands from the Global Wood Density Database CSV.

    User drops the Dryad export at docs/botany/sources/wood_density.csv. Surfaced
    as reference data (mechanics feed sag/flexibility, #20); not flagged.
    """
    path = cache / "wood_density.csv"
    if not path.exists():
        return []
    rows = _read_csv(path)
    if not rows:
        return []
    latin_col = next(
        (c for c in rows[0] if c and c.lower() in ("binomial", "species", "name")),
        None,
    )
    value_col = next(
        (c for c in rows[0] if c and c.lower().startswith("wood density")),
        None,
    )
    if latin_col is None or value_col is None:
        return []
    return extract_per_species_csv(
        path,
        latin_col=latin_col,
        value_col=value_col,
        field="reference.wood_density_g_cm3",
        source="wood_density",
        page="Dryad CSV, per-species 5-95th pct",
        species_latin=load_species_latin(),
        lo_pct=5,
        hi_pct=95,
    )


# Map source key -> extractor. Add PDF-table extractors here as sources are
# parsed (pdfplumber lives behind the `botany` extra; import it lazily inside
# the extractor so the dry run works without it).
EXTRACTORS = {
    "wood_density": _extract_wood_density,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=Path("docs/botany/sources"),
                    help="Source cache produced by fetch_botany_sources.py.")
    ap.add_argument("--only", nargs="*", default=None,
                    help="Restrict to these source keys (default: all extractors).")
    ap.add_argument("--write", action="store_true",
                    help="Merge proposals into literature.yaml (default: dry run).")
    args = ap.parse_args()

    keys = args.only if args.only else sorted(EXTRACTORS)
    proposals: list[Proposal] = []
    for key in keys:
        fn = EXTRACTORS.get(key)
        if fn is None:
            print(f"  (no extractor registered for {key!r})")
            continue
        proposals.extend(fn(args.cache))

    if not proposals:
        print("No proposals — is the cache populated? Run fetch_botany_sources.py first.")
        return 0

    print(f"{'field':32s} {'species':8s} {'value':>18s}  source")
    print("-" * 78)
    for p in proposals:
        sp = p.species or "global"
        print(f"{p.field:32s} {sp:8s} {str(list(p.value)):>18s}  {p.source} ({p.page})")

    if args.write:
        _merge_into_manifest(proposals)
        print("\nwrote proposals into literature.yaml")
    else:
        print("\n(dry run — pass --write to merge into literature.yaml)")
    return 0


def _manifest_path() -> Path:
    return Path(str(resources.files("palubicki.configs").joinpath("literature.yaml")))


def _merge_into_manifest(proposals: list[Proposal]) -> None:
    path = _manifest_path()
    data = yaml.safe_load(path.read_text()) or {}
    ranges = data.setdefault("ranges", {})
    for p in proposals:
        if p.species is None:
            bucket = ranges.setdefault("global", {})
        else:
            bucket = ranges.setdefault("species", {}).setdefault(p.species, {})
        # Dotted field path (e.g. "reference.wood_density_g_cm3") nests; the last
        # segment holds the {value, source, page} entry.
        *parents, leaf = p.field.split(".")
        for seg in parents:
            bucket = bucket.setdefault(seg, {})
        bucket[leaf] = {"value": list(p.value), "source": p.source, "page": p.page}
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


if __name__ == "__main__":
    raise SystemExit(main())
