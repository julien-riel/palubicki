# Distichous phyllotaxy mode — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `"distichous"` as a named phyllotaxis mode (one bud per node, 180° alternation) plus a `distichous_on_plagiotropic` flag that promotes lateral (non-main) axes to distichous regardless of `cfg.mode`. Demonstrate with a new `fir` species preset.

**Architecture:** Touch two source files (`config.py`, `sim/phyllotaxy.py`), add new tests in `tests/sim/test_phyllotaxy.py`, add `fir.yaml` to `src/palubicki/configs/species/`, and register `"fir"` in the species golden parametrize. Existing oak/birch/pine/maple goldens stay byte-identical because the new field defaults `False` and no existing preset sets `mode: distichous`.

**Tech Stack:** Python 3.14, dataclasses with `Literal`, numpy, pytest. Project venv at `.venv/` — prefix every command with `.venv/bin/`.

**Spec:** `docs/superpowers/specs/2026-05-28-distichous-phyllotaxy-design.md`

---

## File map

- **Modify:** `src/palubicki/config.py` (`PhyllotaxyConfig` — mode Literal + new field)
- **Modify:** `src/palubicki/sim/phyllotaxy.py` (`lateral_bud_directions` — effective_mode + distichous branch)
- **Modify:** `tests/sim/test_phyllotaxy.py` (4 new tests)
- **Create:** `src/palubicki/configs/species/fir.yaml`
- **Modify:** `tests/golden/test_species_goldens.py:32` (add `"fir"` to parametrize)
- **Create:** `tests/golden/data/species_fir.sha256` (generated via `--update-goldens`)

---

## Task 1: Distichous mode value + handler

**Files:**
- Modify: `src/palubicki/config.py:110`
- Modify: `src/palubicki/sim/phyllotaxy.py:40-60`
- Test: `tests/sim/test_phyllotaxy.py`

- [ ] **Step 1: Write three failing tests**

Append to `tests/sim/test_phyllotaxy.py`:

```python
def test_distichous_yields_one_direction():
    cfg = PhyllotaxyConfig(mode="distichous", branch_angle_by_order=(45.0,))
    dirs = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0, seed=0, axis_order=0)
    assert dirs.shape == (1, 3)
    assert abs(np.linalg.norm(dirs[0]) - 1.0) < 1e-7


def test_distichous_alternates_180_between_successive_nodes():
    cfg = PhyllotaxyConfig(mode="distichous", branch_angle_by_order=(45.0,))
    g = np.array([0.0, 1.0, 0.0])

    def perp(v):
        p = v - np.dot(v, g) * g
        return p / np.linalg.norm(p)

    d0 = lateral_bud_directions(g, cfg, node_index=0, seed=0, axis_order=0)[0]
    d1 = lateral_bud_directions(g, cfg, node_index=1, seed=0, axis_order=0)[0]
    d2 = lateral_bud_directions(g, cfg, node_index=2, seed=0, axis_order=0)[0]
    assert np.dot(perp(d0), perp(d1)) < -0.999
    assert np.dot(perp(d1), perp(d2)) < -0.999


def test_distichous_ignores_divergence_angle_deg():
    cfg_a = PhyllotaxyConfig(mode="distichous", branch_angle_by_order=(45.0,), divergence_angle_deg=0.0)
    cfg_b = PhyllotaxyConfig(mode="distichous", branch_angle_by_order=(45.0,), divergence_angle_deg=137.5)
    g = np.array([0.0, 1.0, 0.0])
    d_a = lateral_bud_directions(g, cfg_a, node_index=1, seed=0, axis_order=0)
    d_b = lateral_bud_directions(g, cfg_b, node_index=1, seed=0, axis_order=0)
    np.testing.assert_allclose(d_a, d_b, atol=1e-10)
```

- [ ] **Step 2: Run the tests, confirm they fail**

Run: `.venv/bin/pytest tests/sim/test_phyllotaxy.py -k distichous -v`

Expected: collection fails or all three error with `ValueError` from the `Literal` rejecting `"distichous"`, or `pydantic`/`dataclasses` reporting an invalid mode. (Specifically, `PhyllotaxyConfig(mode="distichous", ...)` may raise at construction because `Literal["alternate", "opposite", "whorled", "decussate"]` doesn't accept it. Dataclass `Literal` is documentation-only at runtime, but the `else` branch in `lateral_bud_directions` will raise `ValueError: unknown phyllotaxy mode: 'distichous'`.)

- [ ] **Step 3: Extend the mode Literal in `config.py`**

In `src/palubicki/config.py`, change line 110 from:

```python
    mode: Literal["alternate", "opposite", "whorled", "decussate"] = field(
```

to:

```python
    mode: Literal["alternate", "opposite", "whorled", "decussate", "distichous"] = field(
```

- [ ] **Step 4: Add the distichous branch in `lateral_bud_directions`**

In `src/palubicki/sim/phyllotaxy.py`, replace lines 40–60 (the `if/elif` mode tree and the base_azimuth selection) with:

```python
    if cfg.mode == "alternate":
        k = 1
    elif cfg.mode == "opposite":
        k = 2
    elif cfg.mode == "whorled":
        k = max(1, cfg.whorl_count)
    elif cfg.mode == "decussate":
        k = 2
    elif cfg.mode == "distichous":
        k = 1
    else:
        raise ValueError(f"unknown phyllotaxy mode: {cfg.mode!r}")

    angles = cfg.branch_angle_by_order
    idx = min(int(axis_order), len(angles) - 1)

    if cfg.mode == "decussate":
        base_azimuth = (
            math.radians(cfg.divergence_angle_deg) * node_index
            + (math.pi / 2.0) * (node_index % 2)
        )
    elif cfg.mode == "distichous":
        # Fixed 180° flip per node; divergence_angle_deg is ignored here.
        base_azimuth = math.pi * node_index
    else:
        base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index
```

- [ ] **Step 5: Run the three tests and confirm they pass**

Run: `.venv/bin/pytest tests/sim/test_phyllotaxy.py -k distichous -v`

Expected: 3 passed.

- [ ] **Step 6: Run the full phyllotaxy test file to confirm no regression**

Run: `.venv/bin/pytest tests/sim/test_phyllotaxy.py -v`

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/config.py src/palubicki/sim/phyllotaxy.py tests/sim/test_phyllotaxy.py
git commit -m "feat(sim): add distichous phyllotaxis mode (#2)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Per-axis flag (`distichous_on_plagiotropic`)

**Files:**
- Modify: `src/palubicki/config.py` (`PhyllotaxyConfig`)
- Modify: `src/palubicki/sim/phyllotaxy.py` (`lateral_bud_directions` — effective_mode)
- Test: `tests/sim/test_phyllotaxy.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/sim/test_phyllotaxy.py`:

```python
def test_distichous_on_plagiotropic_only_affects_lateral_axes():
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_by_order=(45.0,),
        divergence_angle_deg=137.5,
        distichous_on_plagiotropic=True,
    )
    g = np.array([0.0, 1.0, 0.0])

    def perp(v):
        p = v - np.dot(v, g) * g
        return p / np.linalg.norm(p)

    # axis_order=0 (main): follows alternate/137.5 — should NOT be antiparallel.
    d0_main = lateral_bud_directions(g, cfg, node_index=0, seed=0, axis_order=0)[0]
    d1_main = lateral_bud_directions(g, cfg, node_index=1, seed=0, axis_order=0)[0]
    cos_main = np.dot(perp(d0_main), perp(d1_main))
    assert cos_main > -0.9, f"main axis was forced to distichous (cos={cos_main})"

    # axis_order=1 (lateral): forced to distichous — must be antiparallel.
    d0_lat = lateral_bud_directions(g, cfg, node_index=0, seed=0, axis_order=1)[0]
    d1_lat = lateral_bud_directions(g, cfg, node_index=1, seed=0, axis_order=1)[0]
    cos_lat = np.dot(perp(d0_lat), perp(d1_lat))
    assert cos_lat < -0.999, f"lateral axis was not distichous (cos={cos_lat})"
```

- [ ] **Step 2: Run the test, confirm it fails**

Run: `.venv/bin/pytest tests/sim/test_phyllotaxy.py::test_distichous_on_plagiotropic_only_affects_lateral_axes -v`

Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'distichous_on_plagiotropic'`.

- [ ] **Step 3: Add the field to `PhyllotaxyConfig`**

In `src/palubicki/config.py`, append (immediately after the `dormant_reserve_count` field, inside the `PhyllotaxyConfig` dataclass body):

```python
    distichous_on_plagiotropic: bool = field(
        default=False,
        metadata={"ui": {"label": "Distichous on lateral axes"}},
    )
```

- [ ] **Step 4: Run the test again, confirm it still fails (now on assertion, not construction)**

Run: `.venv/bin/pytest tests/sim/test_phyllotaxy.py::test_distichous_on_plagiotropic_only_affects_lateral_axes -v`

Expected: FAIL — the lateral-axis assertion fails because the function still uses `cfg.mode` and doesn't consult the new flag.

- [ ] **Step 5: Refactor `lateral_bud_directions` to use `effective_mode`**

In `src/palubicki/sim/phyllotaxy.py`, replace the block from Task 1 (the `if/elif cfg.mode` tree and base_azimuth selection) with one that computes `effective_mode` first:

```python
    # Effective mode: the flag promotes lateral axes (axis_order > 0) to
    # distichous regardless of cfg.mode.
    if cfg.distichous_on_plagiotropic and axis_order > 0:
        effective_mode = "distichous"
    else:
        effective_mode = cfg.mode

    if effective_mode == "alternate":
        k = 1
    elif effective_mode == "opposite":
        k = 2
    elif effective_mode == "whorled":
        k = max(1, cfg.whorl_count)
    elif effective_mode == "decussate":
        k = 2
    elif effective_mode == "distichous":
        k = 1
    else:
        raise ValueError(f"unknown phyllotaxy mode: {effective_mode!r}")

    angles = cfg.branch_angle_by_order
    idx = min(int(axis_order), len(angles) - 1)

    if effective_mode == "decussate":
        base_azimuth = (
            math.radians(cfg.divergence_angle_deg) * node_index
            + (math.pi / 2.0) * (node_index % 2)
        )
    elif effective_mode == "distichous":
        # Fixed 180° flip per node; divergence_angle_deg is ignored here.
        base_azimuth = math.pi * node_index
    else:
        base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index
```

- [ ] **Step 6: Run the test and confirm it passes**

Run: `.venv/bin/pytest tests/sim/test_phyllotaxy.py::test_distichous_on_plagiotropic_only_affects_lateral_axes -v`

Expected: PASS.

- [ ] **Step 7: Run full phyllotaxy test file (no regression)**

Run: `.venv/bin/pytest tests/sim/test_phyllotaxy.py -v`

Expected: all tests pass (the new tests + every previously passing test).

- [ ] **Step 8: Commit**

```bash
git add src/palubicki/config.py src/palubicki/sim/phyllotaxy.py tests/sim/test_phyllotaxy.py
git commit -m "feat(sim): per-axis distichous_on_plagiotropic flag (#2)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: New `fir` preset + golden

**Files:**
- Create: `src/palubicki/configs/species/fir.yaml`
- Modify: `tests/golden/test_species_goldens.py:32`
- Create: `tests/golden/data/species_fir.sha256` (via `--update-goldens`)

- [ ] **Step 1: Create the fir preset YAML**

Create `src/palubicki/configs/species/fir.yaml` with content (derived from pine, swapping the phyllotaxy block):

```yaml
# Abies-shaped sketch — orthotropic trunk, plagiotropic side sprays,
# 2-ranked needles via distichous_on_plagiotropic. Not a faithful Abies model.
envelope:
  shape: cone
  rx: 2.0
  ry: 9.5
  rz: 2.0
  marker_count: 18000
sim:
  internode_length: 0.16
  internode_length_jitter: 0.10
  lambda_apical: 0.88
  alpha_basipetal: 2.5
  max_iterations: 50
  elongation:
    enabled: true
    tau_iterations: 2.5
    age_factor_min: 0.4
    age_factor_decay: 0.7
  sympodial:
    enabled: false
  shade_mortality:
    enabled: true
    light_threshold: 0.12
    n_consecutive_steps: 4
tropism:
  w_perception: 1.0
  w_orthotropy_main: 0.50
  w_orthotropy_lateral: 0.0
  w_gravitropism_main: 0.0
  w_gravitropism_lateral: 0.02
  w_plagiotropism_main: 0.0
  w_plagiotropism_lateral: 1.20
  w_phototropism: 0.15
  w_direction_inertia: 0.8
  axis_decay: 0.9
phyllotaxy:
  mode: alternate
  divergence_angle_deg: 137.5
  branch_angle_by_order: [70.0, 55.0, 40.0, 30.0]
  divergence_jitter_deg: 3.0
  branch_angle_jitter_deg: 3.0
  dormant_reserve_count: 0
  distichous_on_plagiotropic: true
shedding:
  quality_threshold: 0.20
  window: 5
  enabled: true
  reactivation_count: 0
light:
  enabled: true
  k_absorption: 0.65
sag:
  enabled: false
geom:
  ring_sides: 8
  pipe_exponent: 2.30
  r_tip: 0.007
  bark_color: [0.40, 0.28, 0.20]
  bark_texture: "proc:pine_bark"
  leaf_texture: "proc:pine_needle"
  leaf_size: 0.05
  leaf_aspect: 0.025
  leaf_cluster_count: 4
  leaf_splay_deg: 20
  foliage_depth: 3
  leaf_sun_shade_k: 0.0
```

- [ ] **Step 2: Add `"fir"` to the golden parametrize**

In `tests/golden/test_species_goldens.py:32`, change:

```python
@pytest.mark.parametrize("species", ["oak", "pine", "birch", "maple"])
```

to:

```python
@pytest.mark.parametrize("species", ["oak", "pine", "birch", "maple", "fir"])
```

- [ ] **Step 3: Generate the fir golden**

Run: `.venv/bin/pytest tests/golden/test_species_goldens.py::test_species_golden -k fir --update-goldens -v`

Expected: `species_fir.sha256` written to `tests/golden/data/`, test is skipped with message "golden written for fir; re-run without --update-goldens to verify".

- [ ] **Step 4: Verify the fir golden is stable across re-runs**

Run: `.venv/bin/pytest tests/golden/test_species_goldens.py::test_species_golden -k fir -v`

Expected: PASS — re-running the same generator with the same seed produces the same buffer hash. If this step *fails* to skip in step 3 above and instead errors with a config-loading exception (e.g. "unexpected keyword `distichous_on_plagiotropic`"), the YAML loader path in `src/palubicki/config.py` needs to accept the new field — debug before continuing.

- [ ] **Step 5: Verify all existing species goldens (oak/pine/birch/maple) unchanged**

Run: `.venv/bin/pytest tests/golden/test_species_goldens.py -v`

Expected: all 5 tests (oak, pine, birch, maple, fir) pass. If oak/pine/birch/maple fail, the per-axis flag's default-False guard was broken — debug in `lateral_bud_directions` before continuing.

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/configs/species/fir.yaml tests/golden/test_species_goldens.py tests/golden/data/species_fir.sha256
git commit -m "feat(presets): add fir preset using distichous on plagiotropic axes (#2)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Full-repo verification + push

**Files:** none changed — verification only.

- [ ] **Step 1: Run the full fast test suite**

Run: `.venv/bin/pytest -m 'not slow' -q`

Expected: all green.

- [ ] **Step 2: Run the slow suite (goldens + integration)**

Run: `.venv/bin/pytest -m slow -q`

Expected: all green.

- [ ] **Step 3: Confirm the branch is ahead of main and push**

Run:

```bash
git log --oneline main..HEAD
git push
```

Expected: 5 commits visible (Start work on #2, spec, distichous mode, per-axis flag, fir preset). `git push` succeeds against upstream `issue-2-add-explicit-distichous-mode-single-bud`.

- [ ] **Step 4: Mark PR ready and link this as the final review hand-off**

Do *not* mark ready yet — the next step is human review on the open draft PR #15. Leave the PR in draft.

---

## Self-review (already done)

- **Spec coverage:** every section of `2026-05-28-distichous-phyllotaxy-design.md` maps to a task: mode literal (T1), handler (T1), per-axis field (T2), effective_mode logic (T2), fir preset (T3), golden (T3), four unit tests (T1+T2), existing goldens unchanged (T3 step 6). ✓
- **Placeholder scan:** no TBD/TODO/"similar to" — every step has its actual code. ✓
- **Type consistency:** field name `distichous_on_plagiotropic` used identically in config.py, the test, the YAML preset, and the handler. ✓
