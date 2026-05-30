# Per-Species Literature Ranges + Config Tuning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill `ranges.species` in the literature manifest for all 5 species (realigned to North American taxa) with cited, extracted bounds, and tune each `species/*.yaml` so `diagnose --species X` is mostly ✓ on measured metrics.

**Architecture:** Extend `MetricRanges` with 3 architectural fields (already read by `format_report`). Add a `species_latin` map + per-species extractor registry to `extract_botany_values.py`. Populate the manifest from real sources (PDF Silvics/Wood Handbook fetched; CSV exports user-supplied), then iterate the configs against the per-species diagnostic.

**Tech Stack:** Python 3.11+, dataclasses, importlib.resources, PyYAML, pdfplumber (`botany` extra), pytest. Run everything via `.venv/bin/`.

**Reference spec:** `docs/superpowers/specs/2026-05-30-per-species-literature-ranges-design.md`

---

## File Structure

- `src/palubicki/sim/diagnostics.py` — add 3 fields to `MetricRanges` (modify).
- `src/palubicki/configs/literature.yaml` — `species_latin:` + 5 species blocks (modify).
- `scripts/extract_botany_values.py` — `species_latin` loader + per-species extractors (modify).
- `src/palubicki/configs/species/{birch,fir,maple,oak,pine}.yaml` — NA header + lever comment + tuned values (modify).
- `tests/sim/test_metric_ranges.py` — new-field tests (modify).
- `tests/test_extract_botany_values.py` — latin-filter extractor tests (modify).
- `docs/botany/sources.md` — note NA realignment (modify).

---

## Task 1: Add architectural fields to MetricRanges

**Files:**
- Modify: `src/palubicki/sim/diagnostics.py:546-548`
- Test: `tests/sim/test_metric_ranges.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_metric_ranges.py`:

```python
def test_metric_ranges_has_architectural_fields():
    from palubicki.sim.diagnostics import MetricRanges

    fields = {f.name for f in __import__("dataclasses").fields(MetricRanges)}
    assert "tree_height" in fields
    assert "trunk_base_diameter" in fields
    assert "crown_radius" in fields


def test_architectural_fields_default_none():
    from palubicki.sim.diagnostics import MetricRanges

    r = MetricRanges()
    assert r.tree_height is None
    assert r.crown_radius is None
    assert r.trunk_base_diameter is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/sim/test_metric_ranges.py::test_metric_ranges_has_architectural_fields -v`
Expected: FAIL — `tree_height` not in fields.

- [ ] **Step 3: Add the fields**

In `src/palubicki/sim/diagnostics.py`, replace the three existing field lines (546-548) with:

```python
    horton_bifurcation_ratio_mean: tuple[float, float] | None = (3.0, 5.0)
    divergence_angle_deg__order1_mean: tuple[float, float] | None = (130.0, 145.0)
    insertion_angle_deg_vs_parent__order1_mean: tuple[float, float] | None = (30.0, 65.0)
    # Architectural bounds — measured by compute_metrics, read by format_report.
    # Default None (no flag) so global-only behavior is unchanged; populated
    # per-species from the manifest.
    tree_height: tuple[float, float] | None = None
    trunk_base_diameter: tuple[float, float] | None = None
    crown_radius: tuple[float, float] | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/sim/test_metric_ranges.py -v`
Expected: PASS (all, including the 4 pre-existing tests).

- [ ] **Step 5: Verify format_report flags a populated architectural bound**

Run:
```bash
.venv/bin/python -c "
from palubicki.sim.diagnostics import format_report, MetricRanges
r = MetricRanges(tree_height=(4.0, 6.0))
out = format_report({'tree_height': 5.0}, ranges=r, species='oak')
assert '✓' in out, out
print('OK: tree_height in-band flagged ✓')
"
```
Expected: `OK: tree_height in-band flagged ✓`

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/sim/diagnostics.py tests/sim/test_metric_ranges.py
git commit -m "diagnose: add tree_height/trunk_base_diameter/crown_radius bounds to MetricRanges (#32)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Add species_latin map to the manifest + loader

**Files:**
- Modify: `src/palubicki/configs/literature.yaml`
- Modify: `scripts/extract_botany_values.py`
- Test: `tests/test_extract_botany_values.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_extract_botany_values.py`:

```python
def test_load_species_latin_returns_na_taxa():
    m = extract.load_species_latin()
    assert m["oak"] == "Quercus rubra"
    assert m["maple"] == "Acer saccharum"
    assert m["birch"] == "Betula papyrifera"
    assert m["pine"] == "Pinus strobus"
    assert m["fir"] == "Abies balsamea"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_extract_botany_values.py::test_load_species_latin_returns_na_taxa -v`
Expected: FAIL — `load_species_latin` not defined.

- [ ] **Step 3: Add `species_latin` to the manifest**

In `src/palubicki/configs/literature.yaml`, insert this block immediately before the `ranges:` line:

```yaml
# config name -> latin binomial. Single source of truth shared by the extract
# script (CSV/PDF filtering) and the docs. Realigned to North American taxa so
# the free PDF sources (Silvics of North America, Wood Handbook) match.
species_latin:
  birch: "Betula papyrifera"
  fir: "Abies balsamea"
  maple: "Acer saccharum"
  oak: "Quercus rubra"
  pine: "Pinus strobus"

```

- [ ] **Step 4: Add the loader to the extract script**

In `scripts/extract_botany_values.py`, add this function immediately after `_read_csv` (after its closing line):

```python
def load_species_latin() -> dict[str, str]:
    """config name -> latin binomial, from the manifest's species_latin block."""
    text = resources.files("palubicki.configs").joinpath("literature.yaml").read_text()
    return (yaml.safe_load(text) or {}).get("species_latin", {})
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_extract_botany_values.py -v`
Expected: PASS (all 5).

- [ ] **Step 6: Verify the manifest still loads and from_species is unaffected**

Run:
```bash
.venv/bin/python -c "
from palubicki.sim.diagnostics import MetricRanges
assert MetricRanges.from_species(None).divergence_angle_deg__order1_mean == (130.0, 145.0)
print('OK: manifest loads, global bounds intact')
"
```
Expected: `OK: manifest loads, global bounds intact`

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/configs/literature.yaml scripts/extract_botany_values.py tests/test_extract_botany_values.py
git commit -m "data: add species_latin (NA taxa) map + loader to manifest (#32)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Per-species CSV extractor with latin filter

**Files:**
- Modify: `scripts/extract_botany_values.py`
- Test: `tests/test_extract_botany_values.py`

This generalizes extraction from "one global value" to "one band per species,
filtered by latin name". Wood density is the worked example (CSV the user drops in).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_extract_botany_values.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_extract_botany_values.py::test_extract_per_species_filters_by_latin -v`
Expected: FAIL — `extract_per_species_csv` not defined.

- [ ] **Step 3: Implement `extract_per_species_csv`**

In `scripts/extract_botany_values.py`, add this function immediately after `load_species_latin`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_extract_botany_values.py -v`
Expected: PASS (all 6).

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_botany_values.py tests/test_extract_botany_values.py
git commit -m "scripts: per-species CSV extractor filtered by latin name (#32)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Wire wood-density extractor to per-species + register sources

**Files:**
- Modify: `scripts/extract_botany_values.py`

Replace the global-only `_extract_wood_density` with a per-species one using the
new helper, and register the new PDF/CSV sources in the manifest's `sources:`
block so the fetch script knows about them.

- [ ] **Step 1: Replace `_extract_wood_density`**

In `scripts/extract_botany_values.py`, replace the entire body of
`_extract_wood_density` (the function from `def _extract_wood_density` through its
`return [...]`) with:

```python
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
```

- [ ] **Step 2: Add the Silvics + Flora-NA sources to the manifest**

In `src/palubicki/configs/literature.yaml`, inside the `sources:` block, add (after the `silvics:` entry already present):

```yaml
  flora_na:
    cite: "Flora of North America Editorial Committee (1993+). Flora of North America North of Mexico. efloras.org."
    url: "http://www.efloras.org/flora_page.aspx?flora_id=1"
    availability: free
    format: html
```

- [ ] **Step 3: Verify dry-run still works with no cache populated**

Run: `.venv/bin/python scripts/extract_botany_values.py 2>&1 | head -3`
Expected: prints `No proposals — is the cache populated?...` (exit 0, no crash).

- [ ] **Step 4: Verify per-species extraction against a synthetic CSV**

Run:
```bash
mkdir -p /tmp/wdtest && printf 'Binomial,Wood density (g/cm^3)\nQuercus rubra,0.60\nQuercus rubra,0.66\nAcer saccharum,0.62\n' > /tmp/wdtest/wood_density.csv
.venv/bin/python scripts/extract_botany_values.py --cache /tmp/wdtest --only wood_density
```
Expected: a table with `reference.wood_density_g_cm3` rows for `oak` and `maple`.

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_botany_values.py src/palubicki/configs/literature.yaml
git commit -m "scripts: wood-density extractor goes per-species; register flora_na source (#32)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4b: Make manifest merge dotted-path aware (reference.* nesting)

**Files:**
- Modify: `scripts/extract_botany_values.py:170-180` (`_merge_into_manifest`)
- Test: `tests/test_extract_botany_values.py`

A `Proposal.field` like `reference.wood_density_g_cm3` must nest under a
`reference:` map, not become a literal dotted key. The current merge writes
`bucket[p.field]` verbatim — fix it to split on `.`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_extract_botany_values.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_extract_botany_values.py::test_dotted_field_nests_under_reference -v`
Expected: FAIL — dotted key stored verbatim, no `reference` nesting.

- [ ] **Step 3: Fix `_merge_into_manifest`**

In `scripts/extract_botany_values.py`, replace the body of `_merge_into_manifest`
(from `data = yaml.safe_load(...)` through `path.write_text(...)`) with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_extract_botany_values.py -v`
Expected: PASS (all 7).

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_botany_values.py tests/test_extract_botany_values.py
git commit -m "scripts: nest dotted Proposal.field paths (reference.*) on merge (#32)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Seed per-species manifest bounds (angles + phyllotaxy)

**Files:**
- Modify: `src/palubicki/configs/literature.yaml`
- Test: `tests/sim/test_metric_ranges.py`

Phyllotaxy divergence is a botanical constant per mode (not a file extraction):
decussate ~90° (maple), spiral ~137.5° (oak/birch), whorled (pine/fir). Seed
these cited to ABOP. Insertion angles cited to honda1971.

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_metric_ranges.py`:

```python
def test_each_species_has_manifest_entry():
    import yaml
    from importlib import resources

    data = yaml.safe_load(
        resources.files("palubicki.configs").joinpath("literature.yaml").read_text()
    )
    species = data["ranges"]["species"]
    for name in ("birch", "fir", "maple", "oak", "pine"):
        assert name in species, f"{name} missing from ranges.species"


def test_oak_divergence_is_spiral_band():
    from palubicki.sim.diagnostics import MetricRanges

    # Quercus is spiral phyllotaxis -> golden-angle band, not decussate.
    assert MetricRanges.from_species("oak").divergence_angle_deg__order1_mean == (130.0, 145.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/sim/test_metric_ranges.py::test_each_species_has_manifest_entry -v`
Expected: FAIL — only `maple` present.

- [ ] **Step 3: Replace the `ranges.species` block**

In `src/palubicki/configs/literature.yaml`, replace the entire `species:` sub-block under `ranges:` (currently only `maple:`) with:

```yaml
  species:
    birch:  # Betula papyrifera — spiral phyllotaxis, slender
      divergence_angle_deg__order1_mean:
        value: [130.0, 145.0]
        source: abop
        page: "ch. 4 (spiral phyllotaxis, golden angle ~137.5deg)"
    fir:  # Abies balsamea — spiral on the leader, whorled side sprays
      divergence_angle_deg__order1_mean:
        value: [130.0, 145.0]
        source: abop
        page: "ch. 4 (spiral phyllotaxis)"
    maple:  # Acer saccharum — decussate (opposite pairs)
      divergence_angle_deg__order1_mean:
        value: [80.0, 100.0]
        source: abop
        page: "ch. 4 (decussate/opposite phyllotaxis)"
    oak:  # Quercus rubra — spiral phyllotaxis
      divergence_angle_deg__order1_mean:
        value: [130.0, 145.0]
        source: abop
        page: "ch. 4 (spiral phyllotaxis, golden angle ~137.5deg)"
    pine:  # Pinus strobus — whorled (fascicled needles, branch whorls)
      divergence_angle_deg__order1_mean:
        value: [130.0, 145.0]
        source: abop
        page: "ch. 4 (spiral ontogeny underlying branch whorls)"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/sim/test_metric_ranges.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/configs/literature.yaml tests/sim/test_metric_ranges.py
git commit -m "data: seed per-species phyllotaxy divergence bounds for all 5 species (#32)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Fetch PDFs + extract architectural bounds (real data)

**Files:**
- Modify: `src/palubicki/configs/literature.yaml` (architectural + reference values)

This task runs the real pipeline. It is **manual/interactive** — values depend on
the actual PDFs/CSVs. No test code; verification is that `diagnose` flags against
real numbers.

- [ ] **Step 1: Fetch the free PDFs**

Run: `.venv/bin/python scripts/fetch_botany_sources.py --only silvics wood_handbook`
Expected: both download into `docs/botany/sources/` (or print a clear skip reason).

- [ ] **Step 2: Read mature height / crown / dbh per species from Silvics**

Open each species' Silvics chapter (Quercus rubra, Acer saccharum, Betula
papyrifera, Pinus strobus, Abies balsamea). Record mature tree height (m), crown
spread → radius (m), and mature dbh → trunk_base_diameter (m). For each species,
add to its manifest block (example for oak — repeat with real per-species numbers):

```yaml
    oak:  # Quercus rubra
      divergence_angle_deg__order1_mean:
        value: [130.0, 145.0]
        source: abop
        page: "ch. 4 (spiral phyllotaxis, golden angle ~137.5deg)"
      tree_height:
        value: [18.0, 28.0]
        source: silvics
        page: "Quercus rubra — height at maturity"
      crown_radius:
        value: [6.0, 12.0]
        source: silvics
        page: "Quercus rubra — crown spread/2"
      trunk_base_diameter:
        value: [0.3, 0.9]
        source: silvics
        page: "Quercus rubra — mature d.b.h."
```

NOTE: The numbers above are illustrative. Use the values you read from the PDF.
If the simulator's envelope is at a different scale than mature field values
(e.g. height ~5 m vs field ~25 m), record the **literature** value here and note
the scale gap in the Task 7 tuning — do not invent a number to match the sim.

- [ ] **Step 3: Extract wood density per species (if the user supplied the CSV)**

If `docs/botany/sources/wood_density.csv` exists:
Run: `.venv/bin/python scripts/extract_botany_values.py --only wood_density --write`
Expected: `reference.wood_density_g_cm3` entries merged per matched species.
If the CSV is absent, log it and skip — leave a note in the commit message.

- [ ] **Step 4: Verify the per-species diagnostic flags against real bounds**

Run:
```bash
for s in birch fir maple oak pine; do
  echo "=== $s ==="
  .venv/bin/palubicki diagnose --species $s --seed 0 2>/dev/null | grep -E "tree_height|crown_radius|trunk_base|divergence" | head -6
done
```
Expected: each species shows ✓/✗ flags on tree_height/crown_radius/divergence.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/configs/literature.yaml
git commit -m "data: extract per-species architectural + wood-density bounds from sources (#32)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Tune the 5 species configs + lever-map comments

**Files:**
- Modify: `src/palubicki/configs/species/{birch,fir,maple,oak,pine}.yaml`

Iterate each config so measured metrics fall in-band. This is the
diagnose→tune→re-diagnose loop. Do ONE species per sub-step, commit per species.

- [ ] **Step 1: Update NA header + add lever-map comment to each config**

For each of the 5 files, replace the first header comment line with the NA name
and append this lever-map comment block right after the header line. Example for
`oak.yaml` (line 1):

```yaml
# Quercus rubra (northern red oak) — sympodial, étalé, plagiotrope modéré
# Diagnose lever map (metric ✗ -> config knob to turn):
#   tree_height          -> envelope.ry, sim.max_simulation_years, shoot_extension_max
#   crown_radius         -> envelope.rx / envelope.rz
#   trunk_base_diameter  -> geom.pipe_exponent, sim.vigor_diameter_gain
#   divergence (order1)  -> phyllotaxy.mode + phyllotaxy.divergence_angle_deg
#   insertion (order1)   -> phyllotaxy.branch_angle_by_order[0]
#   bifurcation_ratio    -> sim.lambda_apical, sim.alpha_basipetal, shedding.*
```

Use each species' real binomial: birch=Betula papyrifera, fir=Abies balsamea,
maple=Acer saccharum, oak=Quercus rubra, pine=Pinus strobus.

- [ ] **Step 2: Tune maple (decussate) to converge divergence + height/crown**

Run `.venv/bin/palubicki diagnose --species maple --seed 0`. For each ✗ on a
*flagged* metric, turn the mapped knob in `maple.yaml`, re-run, repeat. Target:
divergence order-1 ✓ (decussate ~90°), tree_height ✓, crown_radius ✓.
Accept bifurcation_ratio "in-band or note why not" in the commit message.

- [ ] **Step 3: Commit maple**

```bash
git add src/palubicki/configs/species/maple.yaml
git commit -m "config: tune maple (Acer saccharum) toward literature bounds (#32)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Repeat tune+commit for oak, birch, pine, fir**

For each species, run `.venv/bin/palubicki diagnose --species <s> --seed 0`, turn
mapped knobs until measured metrics are in-band, then:

```bash
git add src/palubicki/configs/species/<s>.yaml
git commit -m "config: tune <s> (<Latin>) toward literature bounds (#32)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Produce a convergence summary**

Run:
```bash
for s in birch fir maple oak pine; do
  echo "=== $s ==="
  .venv/bin/palubicki diagnose --species $s --seed 0 2>/dev/null \
    | grep -E "tree_height|crown_radius|trunk_base|bif_ratio_mean|divergence" | grep -E "✓|✗"
done
```
Expected: majority ✓ on angles + height/crown. Record any persistent ✗ (e.g.
bifurcation_ratio) honestly in the PR description.

---

## Task 8: Update docs + final regression

**Files:**
- Modify: `docs/botany/sources.md`

- [ ] **Step 1: Note the NA realignment in sources.md**

In `docs/botany/sources.md`, after the existing "Version machine" paragraph, add:

```markdown
**Espèces (taxons nord-américains) :** les presets sont calibrés sur *Betula
papyrifera*, *Abies balsamea*, *Acer saccharum*, *Quercus rubra* et *Pinus
strobus* (mapping `species_latin:` dans `literature.yaml`), choisis pour matcher
les sources libres Silvics of North America et Wood Handbook.
```

- [ ] **Step 2: Run the full non-slow suite**

Run: `.venv/bin/python -m pytest -q -p no:cacheprovider -m "not slow"`
Expected: all pass (no regressions).

- [ ] **Step 3: Lint**

Run: `.venv/bin/ruff check scripts/ src/palubicki/sim/diagnostics.py tests/sim/test_metric_ranges.py tests/test_extract_botany_values.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit + push**

```bash
git add docs/botany/sources.md
git commit -m "docs: note NA species realignment in sources.md (#32)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push
```

---

## Definition of done

- `MetricRanges` carries `tree_height`/`trunk_base_diameter`/`crown_radius` (default None).
- `literature.yaml` has `species_latin:` + all 5 species in `ranges.species`, each with cited bounds; architectural/reference values extracted from real sources (or skipped-with-note where a CSV wasn't supplied).
- `extract_botany_values.py` filters CSVs per species by latin name.
- All 5 `species/*.yaml` carry NA headers + lever-map comments and are tuned so measured metrics are mostly in-band.
- Full `not slow` suite green; ruff clean; PR description honest about non-convergences.
