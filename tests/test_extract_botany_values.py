"""Pure extraction helpers for scripts/extract_botany_values.py.

The script's I/O (PDF/CSV reading, manifest writing) is exercised by hand; these
tests pin the numeric-reduction logic that turns a column of observations into a
[lo, hi] bound, which is the part that must stay correct.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "extract_botany_values",
    Path(__file__).resolve().parents[1] / "scripts" / "extract_botany_values.py",
)
extract = importlib.util.module_from_spec(_SPEC)
# Register before exec so @dataclass can resolve cls.__module__ (Python 3.14).
sys.modules[_SPEC.name] = extract
_SPEC.loader.exec_module(extract)


def test_range_from_values_uses_min_max():
    assert extract.range_from_values([3.1, 4.0, 4.9, 3.5]) == (3.1, 4.9)


def test_range_from_values_percentiles_trim_outliers():
    # With a percentile band, a lone outlier shouldn't widen the bound.
    vals = [10.0] * 9 + [1000.0]
    lo, hi = extract.range_from_values(vals, lo_pct=10, hi_pct=90)
    assert lo == 10.0
    assert hi < 1000.0


def test_range_from_values_rejects_empty():
    import pytest

    with pytest.raises(ValueError):
        extract.range_from_values([])


def test_parse_numeric_column_skips_non_numeric():
    rows = [
        {"species": "Acer", "height_m": "12.5"},
        {"species": "Quercus", "height_m": "n/a"},
        {"species": "Pinus", "height_m": "30.0"},
    ]
    assert extract.parse_numeric_column(rows, "height_m") == [12.5, 30.0]


def test_load_species_latin_returns_na_taxa():
    m = extract.load_species_latin()
    assert m["oak"] == "Quercus rubra"
    assert m["maple"] == "Acer saccharum"
    assert m["birch"] == "Betula papyrifera"
    assert m["pine"] == "Pinus strobus"
    assert m["fir"] == "Abies balsamea"
