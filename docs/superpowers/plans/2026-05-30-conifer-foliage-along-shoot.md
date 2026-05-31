# Conifer Foliage Along the Shoot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make pine and fir crowns read as full evergreens by distributing needle clusters *along* each leaf-bearing shoot instead of beading one cluster at each node.

**Architecture:** A new geom knob `needle_cluster_spacing` (meters, default `0.0`) gates the behavior. At `0.0` foliage placement is byte-identical to today (broadleaves untouched). At `> 0`, each leaf-bearing internode is clothed with clusters spaced along its length, capped per internode. The retention rule (which internodes bear leaves) is unchanged — only the density *along* those internodes changes. Per-species recalibration then tunes pine/fir empirically against the render.

**Tech Stack:** Python 3, numpy, dataclass config, pytest. Run everything with the `.venv/bin/` prefix (venv activation does not persist across shells).

**Spec:** `docs/superpowers/specs/2026-05-30-conifer-foliage-along-shoot-design.md`

---

## File Structure

- `src/palubicki/config.py` — `GeomConfig` gains `needle_cluster_spacing: float = 0.0` + validation (Task 1).
- `src/palubicki/geom/leaves.py` — refactor node-collection into `_leaf_bearing_nodes`; `_collect_foliage_sites` gains the along-shoot path; `build_leaves_primitive` threads the param (Task 2).
- `src/palubicki/geom/builder.py` — passes `cfg.geom.needle_cluster_spacing` (Task 2).
- `src/palubicki/configs/species/pine.yaml`, `fir.yaml` — recalibrated (Task 3).
- `tests/geom/test_leaves.py` — new regression + along-shoot count tests (Tasks 1–2).
- `tests/golden/data/species_{pine,fir}.sha256` — re-pinned (Task 4).
- `docs/roadmap.md`, `docs/botany/simulator-gap-analysis.md` — updated (Task 5).

---

### Task 1: Add `needle_cluster_spacing` config field

**Files:**
- Modify: `src/palubicki/config.py` (GeomConfig dataclass ~line 253; validation block ~line 500-505)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
def test_needle_cluster_spacing_default_zero():
    from pathlib import Path
    from palubicki.config import load_config
    cfg = load_config(yaml_path=None, cli_overrides={}, output=Path("/tmp/x.glb"), species="oak")
    assert cfg.geom.needle_cluster_spacing == 0.0


def test_needle_cluster_spacing_negative_rejected():
    import pytest
    from pathlib import Path
    from palubicki.config import load_config, ConfigError
    with pytest.raises(ConfigError, match="needle_cluster_spacing"):
        load_config(
            yaml_path=None,
            cli_overrides={"geom.needle_cluster_spacing": -0.1},
            output=Path("/tmp/x.glb"),
            species="oak",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config.py -k needle_cluster_spacing -v`
Expected: FAIL — `AttributeError: 'GeomConfig' object has no attribute 'needle_cluster_spacing'`

- [ ] **Step 3: Add the field**

In `src/palubicki/config.py`, in `GeomConfig` right after the `foliage_depth` field (~line 253):

```python
    # #36: along-shoot needle distribution. 0.0 = legacy (one cluster per
    # leaf-bearing node; broadleaves). >0 = clothe each leaf-bearing internode
    # with clusters spaced this many meters apart (conifers).
    needle_cluster_spacing: float = field(
        default=0.0, metadata={"ui": {"min": 0.0, "max": 0.5, "step": 0.01}}
    )
```

- [ ] **Step 4: Add validation**

In the GeomConfig validation block (alongside the `leaf_splay_deg` check ~line 504):

```python
        if g.needle_cluster_spacing < 0.0:
            raise ConfigError(
                f"geom.needle_cluster_spacing must be >= 0, got {g.needle_cluster_spacing}"
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -k needle_cluster_spacing -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "feat(config): #36 add geom.needle_cluster_spacing knob (default 0.0)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Distribute needle clusters along the shoot

**Files:**
- Modify: `src/palubicki/geom/leaves.py` (`_collect_foliage_sites` ~line 116-184; `build_leaves_primitive` ~line 30-113)
- Modify: `src/palubicki/geom/builder.py` (~line 56-69)
- Test: `tests/geom/test_leaves.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/geom/test_leaves.py` (it already imports `Bud, BudState, Internode, Node, Tree` and defines `_mat()`):

```python
def _linear_chain(n_internodes, length=1.0):
    """root -> n1 -> ... -> n{n_internodes}(apex). Each internode is_main_axis,
    length `length`. One terminal bud on the apex node."""
    root = Node(position=np.zeros(3))
    tree = Tree(root=root)
    prev = root
    for i in range(1, n_internodes + 1):
        node = Node(position=np.array([0.0, float(i) * length, 0.0]))
        iod = Internode(parent_node=prev, child_node=node, length=length,
                        is_main_axis=True, light_factor=1.0)
        prev.children_internodes.append(iod)
        node.parent_internode = iod
        tree.all_internodes.append(iod)
        prev = node
    bud = Bud(position=prev.position.copy(), direction=np.array([0.0, 1.0, 0.0]),
              axis_order=0, parent_node=prev, state=BudState.ACTIVE)
    prev.terminal_bud = bud
    tree.active_buds.append(bud)
    return tree


def test_spacing_zero_matches_default():
    """needle_cluster_spacing=0.0 is byte-identical to omitting the param."""
    tree = _linear_chain(3)
    p_default = build_leaves_primitive(tree, leaf_size=0.1, material=_mat(), foliage_depth=3)
    p_zero = build_leaves_primitive(tree, leaf_size=0.1, material=_mat(),
                                    foliage_depth=3, needle_cluster_spacing=0.0)
    assert np.array_equal(p_default.positions, p_zero.positions)
    assert np.array_equal(p_default.indices, p_zero.indices)


def test_spacing_zero_one_cluster_per_leaf_node():
    """depth=3 on a 3-internode chain -> 3 leaf-bearing nodes -> 3 ovate clusters
    -> 3 * 17 = 51 verts."""
    tree = _linear_chain(3)
    p = build_leaves_primitive(tree, leaf_size=0.1, material=_mat(),
                               foliage_depth=3, needle_cluster_spacing=0.0)
    assert p.positions.shape == (51, 3)


def test_along_shoot_multiplies_clusters():
    """spacing=0.5 on length-1.0 internodes: floor(1.0/0.5)+1 = 3 clusters each,
    3 leaf-bearing internodes -> 9 clusters -> 9 * 17 = 153 verts."""
    tree = _linear_chain(3)
    p = build_leaves_primitive(tree, leaf_size=0.1, material=_mat(),
                               foliage_depth=3, needle_cluster_spacing=0.5)
    assert p.positions.shape == (153, 3)


def test_along_shoot_caps_per_internode():
    """One long internode (length 10) at fine spacing is capped at 8 clusters."""
    tree = _linear_chain(1, length=10.0)
    p = build_leaves_primitive(tree, leaf_size=0.1, material=_mat(),
                               foliage_depth=1, needle_cluster_spacing=0.1)
    assert p.positions.shape == (8 * 17, 3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/geom/test_leaves.py -k "spacing or along_shoot" -v`
Expected: FAIL — `build_leaves_primitive() got an unexpected keyword argument 'needle_cluster_spacing'`

- [ ] **Step 3: Refactor `_collect_foliage_sites` + add along-shoot path**

In `src/palubicki/geom/leaves.py`, add a module constant near the top (after imports):

```python
_MAX_CLUSTERS_PER_INTERNODE = 8
```

Replace the entire `_collect_foliage_sites` function (lines ~116-184) with:

```python
def _leaf_bearing_nodes(
    tree: Tree, foliage_depth: int
) -> list[tuple[Node, np.ndarray, Internode | None]]:
    """Return (node, direction, source_internode) for every leaf-bearing node:
    living terminal apices plus up to (foliage_depth-1) nodes walked back along
    each apex's parent chain (deduped). This is the retention rule shared by both
    the legacy node-clustered path and the along-shoot path.

    Direction is the apex bud's growth direction for apices, the parent-internode
    tangent for walked-back nodes (matching the historical foliage_depth>1 behavior).
    """
    out: list[tuple[Node, np.ndarray, Internode | None]] = []
    apex_nodes: list[Node] = []
    for bud in tree.active_buds:
        if bud.state == BudState.DEAD:
            continue
        node = bud.parent_node
        if len(node.children_internodes) != 0:
            continue
        out.append((node, np.asarray(bud.direction, dtype=np.float64), node.parent_internode))
        apex_nodes.append(node)

    if foliage_depth <= 1:
        return out

    visited: set[int] = {id(n) for n in apex_nodes}
    for apex in apex_nodes:
        current = apex
        for _ in range(foliage_depth - 1):
            if current.parent_internode is None:
                break
            current = current.parent_internode.parent_node
            if id(current) in visited:
                break
            visited.add(id(current))
            if current.parent_internode is not None:
                parent_node = current.parent_internode.parent_node
                cur_bent = current.position + current.sag_offset
                par_bent = parent_node.position + parent_node.sag_offset
                seg = cur_bent - par_bent
                seg_norm = float(np.linalg.norm(seg))
                direction = seg / seg_norm if seg_norm > 1e-12 else np.array([0.0, 1.0, 0.0])
            else:
                direction = np.array([0.0, 1.0, 0.0])
            out.append((current, np.asarray(direction, dtype=np.float64), current.parent_internode))
    return out


def _collect_foliage_sites(
    tree: Tree, foliage_depth: int, needle_cluster_spacing: float = 0.0
) -> list[tuple[np.ndarray, np.ndarray, Internode | None]]:
    """Return (position, direction, source_internode) for each foliage cluster.

    needle_cluster_spacing == 0 -> one cluster at each leaf-bearing node (legacy).
    needle_cluster_spacing > 0  -> clothe each leaf-bearing internode with clusters
    spaced that many meters apart along the (bent) segment, capped at
    _MAX_CLUSTERS_PER_INTERNODE; the node end is always included.
    """
    if foliage_depth < 1:
        return []
    nodes = _leaf_bearing_nodes(tree, foliage_depth)
    sites: list[tuple[np.ndarray, np.ndarray, Internode | None]] = []
    for node, direction, source_iod in nodes:
        node_pos = np.asarray(node.position + node.sag_offset, dtype=np.float64)
        if needle_cluster_spacing <= 0.0 or source_iod is None:
            sites.append((node_pos, direction, source_iod))
            continue
        parent_node = source_iod.parent_node
        par_pos = np.asarray(parent_node.position + parent_node.sag_offset, dtype=np.float64)
        seg = node_pos - par_pos
        seg_len = float(np.linalg.norm(seg))
        if seg_len < 1e-12:
            sites.append((node_pos, direction, source_iod))
            continue
        seg_dir = seg / seg_len
        n = int(seg_len / needle_cluster_spacing) + 1
        n = max(1, min(_MAX_CLUSTERS_PER_INTERNODE, n))
        for k in range(n):
            f = (k + 1) / n
            sites.append((par_pos + f * seg, seg_dir, source_iod))
    return sites
```

Note: keep the existing `from palubicki.sim.tree import BudState, Internode, Node, Tree` import line as-is (all names already imported).

- [ ] **Step 4: Thread the param through `build_leaves_primitive`**

In `src/palubicki/geom/leaves.py`, add the parameter to the signature (after `foliage_depth: int = 1,` ~line 38):

```python
    needle_cluster_spacing: float = 0.0,
```

And change the call site (line ~63) from:

```python
    sites = _collect_foliage_sites(tree, foliage_depth)
```

to:

```python
    sites = _collect_foliage_sites(tree, foliage_depth, needle_cluster_spacing)
```

- [ ] **Step 5: Thread the param through the builder**

In `src/palubicki/geom/builder.py`, in the `build_leaves_primitive(...)` call (~line 56-69), add after the `foliage_depth=cfg.geom.foliage_depth,` line:

```python
            needle_cluster_spacing=cfg.geom.needle_cluster_spacing,
```

- [ ] **Step 6: Run the new + existing leaf tests**

Run: `.venv/bin/pytest tests/geom/test_leaves.py -v`
Expected: PASS — all pre-existing tests still pass (legacy path unchanged) and the 4 new tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/palubicki/geom/leaves.py src/palubicki/geom/builder.py tests/geom/test_leaves.py
git commit -m "feat(geom): #36 distribute needle clusters along the shoot

Refactor leaf-bearing node collection into _leaf_bearing_nodes; add an
along-shoot path to _collect_foliage_sites gated on needle_cluster_spacing.
Default 0.0 is byte-identical to the legacy node-clustered placement.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Recalibrate pine and fir presets

**Files:**
- Modify: `src/palubicki/configs/species/pine.yaml` (geom block; `foliage_depth`)
- Modify: `src/palubicki/configs/species/fir.yaml` (geom block; `foliage_depth`)

This is an empirical calibration loop (project mindset: pose → observe → correct). Starting values below; iterate until the render reads full.

- [ ] **Step 1: Set pine starting values**

In `pine.yaml`, under `geom:` add `needle_cluster_spacing: 0.10` and raise `foliage_depth` from `3` to `4` (white pine holds needles ~2–3 yr; depth is in internode-steps).

- [ ] **Step 2: Set fir starting values**

In `fir.yaml`, under `geom:` add `needle_cluster_spacing: 0.06` and raise `foliage_depth` from `3` to `7` (balsam fir holds needles ~7–10 yr — this is the bald case and needs the deepest retention).

- [ ] **Step 3: Render and observe**

```bash
for sp in pine fir; do
  .venv/bin/palubicki generate --config src/palubicki/configs/species/$sp.yaml --seed 1 -o /tmp/$sp.glb
  .venv/bin/palubicki preview /tmp/$sp.glb -o /tmp/$sp.png
done
.venv/bin/palubicki diagnose --species pine | grep -E "total_leaf_area|leader_deviation|main_axis|tree_height|crown_radius"
.venv/bin/palubicki diagnose --species fir  | grep -E "total_leaf_area|leader_deviation|main_axis|tree_height|crown_radius"
```

View `/tmp/pine.png` and `/tmp/fir.png`. Acceptance: both read as full evergreens (no bare-branch look), not lumpy/beaded; architecture metrics (`tree_height`, `crown_radius`, `leader_deviation_deg`, `main_axis_continuation_rate`) stay ✓; `total_leaf_area` rises markedly (fir well above its current 1.76; pine well above 30).

- [ ] **Step 4: Iterate**

If still sparse: lower `needle_cluster_spacing` (denser) and/or raise `foliage_depth`. If lumpy/too heavy or render time balloons: raise spacing / lower depth. If conifer leader metrics regress, leave tropism/BH alone — this is a foliage-density change only; adjust foliage knobs. Repeat Step 3 until acceptance is met.

- [ ] **Step 5: Commit**

```bash
git add src/palubicki/configs/species/pine.yaml src/palubicki/configs/species/fir.yaml
git commit -m "configs: #36 clothe pine/fir shoots with along-shoot needles

needle_cluster_spacing + deeper foliage_depth (fir needles persist ~7-10yr)
so conifer crowns read full instead of bare-branched.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Re-pin pine/fir goldens; verify broadleaves unchanged

**Files:**
- Modify: `tests/golden/data/species_pine.sha256`, `tests/golden/data/species_fir.sha256`

- [ ] **Step 1: Confirm broadleaf goldens still pass before re-pinning**

Run: `.venv/bin/pytest tests/golden/test_species_goldens.py -k "oak or maple or birch" -v`
Expected: PASS — oak/maple/birch unchanged (their configs have no `needle_cluster_spacing`, so foliage placement is byte-identical).

If any broadleaf FAILS, stop — the legacy path was not preserved; revisit Task 2.

- [ ] **Step 2: Confirm pine/fir goldens now mismatch (intended)**

Run: `.venv/bin/pytest tests/golden/test_species_goldens.py -k "pine or fir" -v`
Expected: FAIL — golden mismatch for pine and fir (geometry changed on purpose).

- [ ] **Step 3: Re-pin only pine + fir**

Run: `.venv/bin/pytest tests/golden/test_species_goldens.py -k "pine or fir" --update-goldens`
Then verify only those two files changed:

Run: `git diff --stat tests/golden/data/`
Expected: only `species_pine.sha256` and `species_fir.sha256` appear.

- [ ] **Step 4: Verify the full golden + diagnostics suite is green**

Run: `.venv/bin/pytest tests/golden/ -v`
Expected: PASS (all species verify against the re-pinned hashes; `test_goldens.py` oak EXPECTED_HASH unaffected).

- [ ] **Step 5: Commit**

```bash
git add tests/golden/data/species_pine.sha256 tests/golden/data/species_fir.sha256
git commit -m "test(golden): #36 re-pin pine/fir species goldens (along-shoot foliage)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5 (optional polish): per-site azimuth to break needle banding

Only do this if the Task 3 render shows needles banding in one plane along the shoot. If the cluster splay already reads natural, **skip** — YAGNI.

**Files:**
- Modify: `src/palubicki/geom/leaves.py` (`_emit_leaf_cluster` and the `build_leaves_primitive` loop)
- Test: `tests/geom/test_leaves.py`

- [ ] **Step 1: Write a failing test**

```python
def test_azimuth_offset_rotates_cluster():
    """A nonzero per-site azimuth changes blade positions (breaks banding)."""
    tree = _linear_chain(1, length=10.0)
    p = build_leaves_primitive(tree, leaf_size=0.1, material=_mat(),
                               foliage_depth=1, needle_cluster_spacing=0.1,
                               leaf_cluster_count=4, leaf_shape="linear", splay_deg=20.0)
    # 8 capped clusters along the shoot must not all share one azimuth phase:
    # the x/z spread across cluster centers must be non-degenerate.
    xs = p.positions[:, 0]
    zs = p.positions[:, 2]
    assert xs.std() > 1e-3 and zs.std() > 1e-3
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/geom/test_leaves.py::test_azimuth_offset_rotates_cluster -v`
Expected: FAIL (clusters share one azimuth phase → one of the stds is ~0).

- [ ] **Step 3: Add a golden-angle azimuth per along-shoot site**

In `_collect_foliage_sites`, change the along-shoot tuple to carry an azimuth and have `build_leaves_primitive` pass it to `_emit_leaf_cluster`, rotating the cluster basis around `direction` by `azimuth`. Use a 4-tuple `(pos, dir, source_iod, azimuth)`; legacy sites use `azimuth=0.0` (rotation by 0 rad is exact identity → byte-identical preserved). Increment azimuth by the golden angle `2.399963` rad per along-shoot cluster index.

Concretely: in the along-shoot loop, `sites.append((par_pos + f * seg, seg_dir, source_iod, (k * 2.399963) % (2 * math.pi)))`; legacy appends `(..., 0.0)`. Update the `build_leaves_primitive` unpack to `for i, (center, direction, source_iod, azimuth) in enumerate(sites)` and add an `azimuth` parameter to `_emit_leaf_cluster` that rotates the two perpendicular basis vectors `e1, e2` around `direction`: `e1' = e1*cos(az) + e2*sin(az)`, `e2' = -e1*sin(az) + e2*cos(az)`.

- [ ] **Step 4: Run the azimuth test + the byte-identical regression**

Run: `.venv/bin/pytest tests/geom/test_leaves.py -k "azimuth or spacing_zero" -v`
Expected: PASS — `test_azimuth_offset_rotates_cluster` passes AND `test_spacing_zero_matches_default` still passes (azimuth 0 = identity).

- [ ] **Step 5: Re-render, re-pin pine/fir goldens (geometry changed again)**

Run Task 3 Step 3 render commands, visually confirm banding gone, then:
`.venv/bin/pytest tests/golden/test_species_goldens.py -k "pine or fir" --update-goldens`
and `git diff --stat tests/golden/data/` (only pine+fir).

- [ ] **Step 6: Commit**

```bash
git add src/palubicki/geom/leaves.py tests/geom/test_leaves.py tests/golden/data/species_pine.sha256 tests/golden/data/species_fir.sha256
git commit -m "feat(geom): #36 golden-angle azimuth per along-shoot cluster (break banding)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Update docs + finalize PR

**Files:**
- Modify: `docs/roadmap.md`, `docs/botany/simulator-gap-analysis.md`

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/pytest -q`
Expected: PASS (all green). Also run `.venv/bin/ruff check .` — expected: clean.

- [ ] **Step 2: Update roadmap**

In `docs/roadmap.md`: remove `#36` from "À faire (dans l'ordre)" (item 1) and add a row to the "Fait" table: `| #36 | Couronne conifère pleine : aiguilles réparties le long du rameau (needle_cluster_spacing) + rétention par espèce | #51 |`. Re-check the ordering of the remaining "À faire" items (#37 light grid is the new first).

- [ ] **Step 3: Update gap analysis**

In `docs/botany/simulator-gap-analysis.md`: flip the conifer-foliage / needle-density row(s) toward ✅ with the new behavior, refresh the section verdict and the "Last reviewed" line to 2026-05-30. If no row maps to conifer foliage density, add a short note under the foliage section describing along-shoot needle distribution.

- [ ] **Step 4: Note the superseded diagnosis on the PR**

Add a PR comment (or update the PR body) recording that #36's original title (BH winner-take-all starves laterals) was superseded: #43/#48 fixed branch count, and the residual sparseness was a foliage-modeling issue, fixed here by along-shoot needle distribution. Reference the spec.

```bash
gh pr comment 51 -R julien-riel/palubicki --body "Re-diagnosed during implementation: BH no longer starves laterals (#43/#48 gave pine 19k+ nodes). The residual sparse-crown symptom was a foliage-modeling issue — needles beaded at nodes on only the last \`foliage_depth\` internodes, and fir's depth was far too shallow for its ~7-10yr needle retention. Fixed by distributing needle clusters along the shoot (new \`needle_cluster_spacing\` knob) + per-species recalibration. Design: docs/superpowers/specs/2026-05-30-conifer-foliage-along-shoot-design.md"
```

- [ ] **Step 5: Commit docs**

```bash
git add docs/roadmap.md docs/botany/simulator-gap-analysis.md
git commit -m "docs: #36 mark conifer foliage along-shoot done; update gap analysis

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Push and mark PR ready**

```bash
git push
gh pr ready 51 -R julien-riel/palubicki
```

---

## Notes for the implementer

- **Why `needle_cluster_spacing` in meters, not a count:** internode lengths vary ~30× (proximal ~0.59 m, distal ~0.02 m). Meters give uniform visual density; the per-internode cap (`_MAX_CLUSTERS_PER_INTERNODE = 8`) bounds geometry on long proximal internodes.
- **The byte-identical guarantee is load-bearing:** broadleaf goldens (oak/maple/birch) and the oak `EXPECTED_HASH` in `tests/golden/test_goldens.py` must not change. The default-`0.0` legacy path and azimuth-0 = identity are what protect them. If a broadleaf golden moves, a refactor leaked into the legacy path — fix before re-pinning anything.
- **Out of scope:** `leaf_age`/`LeafState`/clock-tied shedding is #14; BH allocation is healthy. Do not touch `bh.py`.
