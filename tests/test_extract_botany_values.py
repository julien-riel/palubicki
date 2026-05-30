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


def test_extract_per_species_filters_by_latin(tmp_path):
    csv_path = tmp_path / "wood_density.csv"
    csv_path.write_text(
        "Binomial,Wood density (g/cm^3)\n"
        "Quercus rubra,0.60\n"
        "Quercus rubra,0.64\n"
        "Acer saccharum,0.62\n"
        "Pinus strobus,0.34\n"
    )
    species_latin = {"oak": "Quercus rubra", "maple": "Acer saccharum",
                     "pine": "Pinus strobus"}
    props = extract.extract_per_species_csv(
        csv_path,
        latin_col="Binomial",
        value_col="Wood density (g/cm^3)",
        field="wood_density_g_cm3",
        source="wood_density",
        page="Dryad CSV",
        species_latin=species_latin,
    )
    by_species = {p.species: p for p in props}
    assert by_species["oak"].value == (0.6, 0.64)
    assert by_species["pine"].value == (0.34, 0.34)
    # A species with no matching rows yields no proposal.
    assert "birch" not in by_species


def test_dotted_field_nests_under_reference(tmp_path, monkeypatch):
    manifest = tmp_path / "literature.yaml"
    manifest.write_text("ranges:\n  global: {}\n  species: {}\n")
    monkeypatch.setattr(extract, "_manifest_path", lambda: manifest)

    extract._merge_into_manifest([
        extract.Proposal("reference.wood_density_g_cm3", "oak", (0.6, 0.66),
                         "wood_density", "Dryad CSV"),
        extract.Proposal("tree_height", "oak", (18.0, 28.0), "silvics", "p.1"),
    ])

    import yaml
    data = yaml.safe_load(manifest.read_text())
    oak = data["ranges"]["species"]["oak"]
    assert oak["reference"]["wood_density_g_cm3"]["value"] == [0.6, 0.66]
    assert oak["tree_height"]["value"] == [18.0, 28.0]
    assert "reference.wood_density_g_cm3" not in oak
