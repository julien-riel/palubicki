# Tree-Diagnostics Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only diagnostic pass `compute_metrics(tree, *, cfg=None)` and CLI subcommand `palubicki diagnose` that computes structural metrics (Strahler/Horton, angles, counts, architecture, leaf area) for a generated `Tree`, with literature-range ✓/✗ flags and multi-seed comparison.

**Architecture:** Approach A+C from the spec — one self-contained module `sim/diagnostics.py` (registry-free, single-function entry point) + a small refactor extracting `compute_effective_leaf_size` from `geom/leaves.py` so the harness and renderer share one source of truth for sun/shade leaf scaling. CLI subcommand `diagnose` mirrors `_cmd_generate` for config loading.

**Tech Stack:** Python 3, numpy, argparse, pytest. No new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-05-27-tree-diagnostics-design.md` (commit `0830444`).

---

## Conventions for every task

- **Repo root:** `/Users/julienriel/src/palubicki`.
- **Branch:** `issue-1-diagnostic-harness-for-generated-tree` (already checked out).
- **Activate the venv** for every shell command that runs `pytest` or `python`: prefix the command with `.venv/bin/` (e.g. `.venv/bin/pytest …`). The venv does not persist between Bash invocations.
- **TDD strict order:** within each task, every test is *written first*, *run to confirm failure*, then implementation lands, then the test is *re-run to confirm passing*, then commit. Do not skip the red step.
- **Commit messages:** follow the repo's Conventional-Commits style — `feat(sim): …`, `test(sim): …`, `refactor(geom): …`, `feat(cli): …`. Add the `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer.
- **Don't delete any goldens.** This is one of the spec's acceptance criteria; the existing golden suite must remain unchanged.

---

## File structure (locked before tasks begin)

| File | Status | Responsibility |
|---|---|---|
| `src/palubicki/sim/diagnostics.py` | NEW | `compute_metrics`, `format_report`, `MetricRanges`, all metric helpers, internal walkers |
| `src/palubicki/geom/leaves.py` | MODIFY | Extract `compute_effective_leaf_size` (public); `build_leaves_primitive` calls it |
| `src/palubicki/cli.py` | MODIFY | Add `diagnose` subparser (~25 LOC) and `_cmd_diagnose` handler (~30 LOC); add `_parse_seed_list` |
| `tests/sim/test_diagnostics.py` | NEW | Tests #1–#15 from spec (unit + integration) |
| `tests/test_cli.py` | MODIFY | Append tests #16–#19 |

No other files touched. `simulate()` is not modified. Configuration is not modified.

---

## Task 1: Module skeleton + Strahler/Horton

**Goal:** Land `compute_metrics(Tree)` returning a dict with the Strahler keys populated. Internal BFS walkers exist as private helpers and are exercised through Strahler tests.

**Files:**
- Create: `src/palubicki/sim/diagnostics.py`
- Create: `tests/sim/test_diagnostics.py`

- [ ] **Step 1.1: Create the test file with a Y-shape Strahler test (test #1, first half).**

```python
# tests/sim/test_diagnostics.py
from __future__ import annotations

import numpy as np
import pytest

from palubicki.sim.diagnostics import compute_metrics
from palubicki.sim.tree import Internode, Node, Tree


def _link(parent: Node, child: Node, *, axis_order: int = 0,
          is_main_axis: bool = True) -> Internode:
    """Create + bidirectionally link an internode between parent and child."""
    iod = Internode(
        parent_node=parent, child_node=child,
        length=float(np.linalg.norm(child.position - parent.position)),
        is_main_axis=is_main_axis,
    )
    parent.children_internodes.append(iod)
    child.parent_internode = iod
    return iod


def _make_tree_y_shape() -> Tree:
    """Trunk + two equal leaf branches:

           c1     c2
            \\   /
             m
             |
             root
    """
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    c1 = Node(position=np.array([0.5, 1.5, 0.0]))
    c2 = Node(position=np.array([-0.5, 1.5, 0.0]))
    tree = Tree(root=root)
    trunk = _link(root, mid, axis_order=0, is_main_axis=True)
    # Two laterals at the fork — neither marked main axis (terminal fork).
    b1 = _link(mid, c1, axis_order=1, is_main_axis=False)
    b2 = _link(mid, c2, axis_order=1, is_main_axis=False)
    tree.all_internodes.extend([trunk, b1, b2])
    return tree


def test_strahler_y_shape():
    tree = _make_tree_y_shape()
    m = compute_metrics(tree)
    assert m["strahler_order_max"] == 2
    assert m["strahler_order_histogram"] == {1: 2, 2: 1}
    # Bifurcation ratio: count(1) / count(2) = 2 / 1 = 2.0
    assert m["horton_bifurcation_ratio"] == {1: 2.0}
    assert m["horton_bifurcation_ratio_mean"] == pytest.approx(2.0)
```

- [ ] **Step 1.2: Run the test, confirm `ModuleNotFoundError: palubicki.sim.diagnostics`.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -v`
Expected: collection error / ModuleNotFoundError.

- [ ] **Step 1.3: Create `diagnostics.py` with module skeleton + walkers + Strahler.**

```python
# src/palubicki/sim/diagnostics.py
from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from palubicki.sim.tree import BudState, Internode, Node, Tree

if TYPE_CHECKING:
    from palubicki.config import Config


# ── Internal walkers ──────────────────────────────────────────────────────

def _walk_nodes(root: Node) -> list[Node]:
    out: list[Node] = []
    q: deque[Node] = deque([root])
    while q:
        n = q.popleft()
        out.append(n)
        for iod in n.children_internodes:
            q.append(iod.child_node)
    return out


def _walk_internodes(root: Node) -> list[Internode]:
    out: list[Internode] = []
    q: deque[Internode] = deque(root.children_internodes)
    while q:
        iod = q.popleft()
        out.append(iod)
        for c in iod.child_node.children_internodes:
            q.append(c)
    return out


# ── Strahler / Horton ─────────────────────────────────────────────────────

def _strahler_orders(root: Node) -> dict[int, int]:
    """Return {id(Internode): order}. Empty if root has no children."""
    orders: dict[int, int] = {}

    def visit(iod: Internode) -> int:
        kids = iod.child_node.children_internodes
        if not kids:
            order = 1
        else:
            child_orders = [visit(c) for c in kids]
            mx = max(child_orders)
            order = mx + 1 if child_orders.count(mx) > 1 else mx
        orders[id(iod)] = order
        return order

    for iod in root.children_internodes:
        visit(iod)
    return orders


def _strahler_metrics(root: Node) -> dict:
    orders = _strahler_orders(root)
    if not orders:
        return {
            "strahler_order_max": 0,
            "strahler_order_histogram": {},
            "horton_bifurcation_ratio": {},
            "horton_bifurcation_ratio_mean": float("nan"),
        }
    hist: dict[int, int] = defaultdict(int)
    for o in orders.values():
        hist[o] += 1
    hist_d = dict(sorted(hist.items()))
    order_max = max(hist_d)
    ratios: dict[int, float] = {}
    for n in range(1, order_max):
        if hist_d.get(n + 1, 0) > 0:
            ratios[n] = hist_d[n] / hist_d[n + 1]
    if ratios:
        # Geometric mean
        log_sum = sum(math.log(r) for r in ratios.values())
        ratio_mean = math.exp(log_sum / len(ratios))
    else:
        ratio_mean = float("nan")
    return {
        "strahler_order_max": order_max,
        "strahler_order_histogram": hist_d,
        "horton_bifurcation_ratio": ratios,
        "horton_bifurcation_ratio_mean": ratio_mean,
    }


# ── Public entry point ────────────────────────────────────────────────────

def compute_metrics(
    tree: "Tree | list[Tree]",
    *,
    cfg: "Config | None" = None,
) -> dict:
    """Compute structural metrics for one or many trees.

    Tree     → flat dict per the schema in docs/superpowers/specs/
                2026-05-27-tree-diagnostics-design.md.
    list[Tree] → aggregated dict (mean / stddev / per_seed at each leaf).

    `cfg` is optional; only consumed by total_leaf_area.
    """
    if isinstance(tree, list):
        # Multi-seed path lands in Task 7. Stub for now.
        raise NotImplementedError("multi-seed compute_metrics arrives in Task 7")

    out: dict = {}
    out.update(_strahler_metrics(tree.root))
    return out
```

- [ ] **Step 1.4: Run the test, confirm pass.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -v`
Expected: PASS.

- [ ] **Step 1.5: Add the second half of test #1 (deeper tree where unique-max rule matters).**

```python
# Append to tests/sim/test_diagnostics.py

def _make_pectinate_3level() -> Tree:
    """A pectinate-style tree:

              g
             /
            f---leaf3
           /
          e---leaf2
         /
        d---leaf1
        |
        root

    Three forks; each non-leaf has children of orders (1, k) where
    k grows from 1 → 2 → 3 → ... Strahler order at root = 2
    (the unique-max rule keeps each internal node at max+0 since
    the higher-order child is unique at every fork).
    """
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    d = Node(position=np.array([0.0, 1.0, 0.0]))
    leaf1 = Node(position=np.array([0.5, 1.0, 0.0]))
    e = Node(position=np.array([0.0, 2.0, 0.0]))
    leaf2 = Node(position=np.array([0.5, 2.0, 0.0]))
    f = Node(position=np.array([0.0, 3.0, 0.0]))
    leaf3 = Node(position=np.array([0.5, 3.0, 0.0]))
    g = Node(position=np.array([0.0, 4.0, 0.0]))

    tree = Tree(root=root)
    trunk = _link(root, d, axis_order=0, is_main_axis=True)
    l1 = _link(d, leaf1, axis_order=1, is_main_axis=False)
    main1 = _link(d, e, axis_order=0, is_main_axis=True)
    l2 = _link(e, leaf2, axis_order=1, is_main_axis=False)
    main2 = _link(e, f, axis_order=0, is_main_axis=True)
    l3 = _link(f, leaf3, axis_order=1, is_main_axis=False)
    main3 = _link(f, g, axis_order=0, is_main_axis=True)
    tree.all_internodes.extend([trunk, l1, main1, l2, main2, l3, main3])
    return tree


def test_strahler_pectinate_unique_max_rule():
    tree = _make_pectinate_3level()
    m = compute_metrics(tree)
    # main3, l3, l2, l1 are all leaves (order 1). main2 has children
    # (main3, l3): both order 1 → tie → main2 is order 2. main1's children
    # (main2, l2): main2=2, l2=1 → unique max → main1 is order 2. trunk's
    # children (main1, l1): main1=2, l1=1 → unique max → trunk is order 2.
    assert m["strahler_order_max"] == 2
    assert m["strahler_order_histogram"] == {1: 4, 2: 3}
    # ratio 1→2 = 4/3
    assert m["horton_bifurcation_ratio"][1] == pytest.approx(4.0 / 3.0)
```

- [ ] **Step 1.6: Run the test, confirm pass.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py::test_strahler_pectinate_unique_max_rule -v`
Expected: PASS.

- [ ] **Step 1.7: Add tests #2 and #3 (single-internode and empty tree).**

```python
# Append to tests/sim/test_diagnostics.py

def test_strahler_single_internode():
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    child = Node(position=np.array([0.0, 1.0, 0.0]))
    tree = Tree(root=root)
    iod = _link(root, child, axis_order=0, is_main_axis=True)
    tree.all_internodes.append(iod)
    m = compute_metrics(tree)
    assert m["strahler_order_max"] == 1
    assert m["strahler_order_histogram"] == {1: 1}
    assert m["horton_bifurcation_ratio"] == {}
    assert math.isnan(m["horton_bifurcation_ratio_mean"])


def test_strahler_empty_tree():
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    tree = Tree(root=root)
    m = compute_metrics(tree)
    assert m["strahler_order_max"] == 0
    assert m["strahler_order_histogram"] == {}
    assert m["horton_bifurcation_ratio"] == {}
    assert math.isnan(m["horton_bifurcation_ratio_mean"])
```

Add `import math` at the top of the test file if not already present.

- [ ] **Step 1.8: Run all diagnostics tests, confirm pass.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -v`
Expected: 4 PASS.

- [ ] **Step 1.9: Commit.**

```bash
git add src/palubicki/sim/diagnostics.py tests/sim/test_diagnostics.py
git commit -m "$(cat <<'EOF'
feat(sim): diagnostics module skeleton + Strahler/Horton metrics

First slice of the read-only diagnostics harness for #1. Adds the
module entrypoint, internal BFS walkers, and Horton-Strahler order
computation with unique-max rule. Covers tests #1–#3 from the spec
(Y-shape, pectinate, single-internode, empty).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Insertion-angle metrics

**Goal:** Two new keys `insertion_angle_deg_vs_parent` and `insertion_angle_deg_vs_main_sibling` populated by `compute_metrics`.

**Files:**
- Modify: `src/palubicki/sim/diagnostics.py`
- Modify: `tests/sim/test_diagnostics.py`

- [ ] **Step 2.1: Write test #4 — insertion angle vs parent at 45°.**

```python
# Append to tests/sim/test_diagnostics.py

def _make_trunk_with_lateral(branch_dir: np.ndarray, branch_axis_order: int = 1,
                              branch_is_main_axis: bool = False) -> Tree:
    """Trunk along +Y; one lateral at the trunk's child node, pointing in
    `branch_dir` (any vector, not necessarily unit-length)."""
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    branch_dir = np.asarray(branch_dir, dtype=np.float64)
    branch_dir = branch_dir / np.linalg.norm(branch_dir)
    lat_end = mid.position + branch_dir
    lat_node = Node(position=lat_end)
    tree = Tree(root=root)
    trunk = _link(root, mid, axis_order=0, is_main_axis=True)
    lat = _link(mid, lat_node, axis_order=branch_axis_order,
                is_main_axis=branch_is_main_axis)
    tree.all_internodes.extend([trunk, lat])
    return tree


def test_insertion_angle_vs_parent_45():
    # Lateral at 45° in the XZ plane relative to trunk (+Y direction).
    # cos(45°) = √2/2, so branch_dir = (sin45, cos45, 0) gives 45°.
    tree = _make_trunk_with_lateral(
        branch_dir=np.array([math.sin(math.radians(45.0)),
                              math.cos(math.radians(45.0)), 0.0]),
    )
    m = compute_metrics(tree)
    assert 1 in m["insertion_angle_deg_vs_parent"]
    stats = m["insertion_angle_deg_vs_parent"][1]
    assert stats["mean"] == pytest.approx(45.0, abs=1e-6)
    assert stats["stddev"] == pytest.approx(0.0, abs=1e-9)
    assert stats["n"] == 1
```

- [ ] **Step 2.2: Run the test, confirm `KeyError` or similar failure.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py::test_insertion_angle_vs_parent_45 -v`
Expected: FAIL (`KeyError: 'insertion_angle_deg_vs_parent'`).

- [ ] **Step 2.3: Implement insertion-angle helpers in `diagnostics.py`.**

Add the following to `src/palubicki/sim/diagnostics.py` (after `_strahler_metrics`, before `compute_metrics`):

```python
# ── Geometry helpers ──────────────────────────────────────────────────────

def _tangent(iod: Internode) -> np.ndarray:
    """Unit vector from parent_node to child_node. Returns +Y for degenerate
    (zero-length) internodes — they shouldn't exist but we don't crash."""
    v = np.asarray(iod.child_node.position - iod.parent_node.position,
                   dtype=np.float64)
    n = float(np.linalg.norm(v))
    if n < 1e-12:
        return np.array([0.0, 1.0, 0.0])
    return v / n


def _angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    """Angle in degrees between two unit vectors, in [0, 180]."""
    c = float(np.clip(np.dot(a, b), -1.0, 1.0))
    return math.degrees(math.acos(c))


def _stats(values: list[float]) -> dict:
    """Return {mean, stddev, n}. stddev is population stddev (ddof=0)."""
    n = len(values)
    if n == 0:
        return {"mean": float("nan"), "stddev": float("nan"), "n": 0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(arr.mean()),
        "stddev": float(arr.std(ddof=0)),
        "n": n,
    }


# ── Insertion angles ──────────────────────────────────────────────────────

def _insertion_angle_metrics(internodes: list[Internode]) -> dict:
    """For each internode L:
      - vs_parent:  angle(L tangent, L.parent_node.parent_internode tangent)
                    skipped if L.parent_node has no incoming internode.
      - vs_main_sibling: angle(L tangent, sibling tangent) where the sibling
                    is the unique child of L.parent_node with is_main_axis=True
                    and is not L itself. Skipped when no such sibling exists.
    Both grouped by L.axis_order.
    """
    by_parent: dict[int, list[float]] = defaultdict(list)
    by_main: dict[int, list[float]] = defaultdict(list)

    for L in internodes:
        L_t = _tangent(L)
        node = L.parent_node

        incoming = node.parent_internode
        if incoming is not None:
            by_parent[L.axis_order].append(_angle_deg(L_t, _tangent(incoming)))

        main_sib: Internode | None = None
        for c in node.children_internodes:
            if c is L:
                continue
            if c.is_main_axis:
                main_sib = c
                break
        if main_sib is not None:
            by_main[L.axis_order].append(_angle_deg(L_t, _tangent(main_sib)))

    return {
        "insertion_angle_deg_vs_parent": {k: _stats(v) for k, v in by_parent.items()},
        "insertion_angle_deg_vs_main_sibling": {k: _stats(v) for k, v in by_main.items()},
    }
```

Update `compute_metrics` to fold the new metrics in:

```python
def compute_metrics(
    tree: "Tree | list[Tree]",
    *,
    cfg: "Config | None" = None,
) -> dict:
    if isinstance(tree, list):
        raise NotImplementedError("multi-seed compute_metrics arrives in Task 7")

    internodes = _walk_internodes(tree.root)
    out: dict = {}
    out.update(_strahler_metrics(tree.root))
    out.update(_insertion_angle_metrics(internodes))
    return out
```

- [ ] **Step 2.4: Run the test, confirm pass.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py::test_insertion_angle_vs_parent_45 -v`
Expected: PASS.

- [ ] **Step 2.5: Write test #5 — insertion angle vs main sibling.**

```python
# Append to tests/sim/test_diagnostics.py

def test_insertion_angle_vs_main_sibling_60():
    """Trunk +Y up to mid; mid has a main-axis continuation also at +Y, plus
    a lateral at 60° from the continuation. Angle vs parent = 60°, angle vs
    main_sibling = 60° (parent and main_sibling happen to be colinear here).
    """
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    top = Node(position=np.array([0.0, 2.0, 0.0]))
    angle = math.radians(60.0)
    lat_dir = np.array([math.sin(angle), math.cos(angle), 0.0])
    lat_node = Node(position=mid.position + lat_dir)

    tree = Tree(root=root)
    trunk = _link(root, mid, axis_order=0, is_main_axis=True)
    cont = _link(mid, top, axis_order=0, is_main_axis=True)
    lat = _link(mid, lat_node, axis_order=1, is_main_axis=False)
    tree.all_internodes.extend([trunk, cont, lat])

    m = compute_metrics(tree)
    p_stats = m["insertion_angle_deg_vs_parent"][1]
    s_stats = m["insertion_angle_deg_vs_main_sibling"][1]
    assert p_stats["mean"] == pytest.approx(60.0, abs=1e-6)
    assert p_stats["n"] == 1
    assert s_stats["mean"] == pytest.approx(60.0, abs=1e-6)
    assert s_stats["n"] == 1


def test_insertion_angle_vs_main_sibling_differs_from_vs_parent():
    """Lateral 60° off main-sibling (which itself points 30° off trunk).
    Trunk +Y; main-sibling at 30° in +X half-plane; lateral at 30° in -X
    half-plane → 60° vs main-sibling, but 30° vs parent (trunk)."""
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    mid = Node(position=np.array([0.0, 1.0, 0.0]))
    a30 = math.radians(30.0)
    main_dir = np.array([math.sin(a30), math.cos(a30), 0.0])
    lat_dir = np.array([-math.sin(a30), math.cos(a30), 0.0])
    top = Node(position=mid.position + main_dir)
    lat_node = Node(position=mid.position + lat_dir)

    tree = Tree(root=root)
    trunk = _link(root, mid, axis_order=0, is_main_axis=True)
    cont = _link(mid, top, axis_order=0, is_main_axis=True)
    lat = _link(mid, lat_node, axis_order=1, is_main_axis=False)
    tree.all_internodes.extend([trunk, cont, lat])

    m = compute_metrics(tree)
    assert m["insertion_angle_deg_vs_parent"][1]["mean"] == pytest.approx(30.0, abs=1e-6)
    assert m["insertion_angle_deg_vs_main_sibling"][1]["mean"] == pytest.approx(60.0, abs=1e-6)
```

- [ ] **Step 2.6: Run the two new tests, confirm pass.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -v -k insertion`
Expected: 3 PASS.

- [ ] **Step 2.7: Commit.**

```bash
git add src/palubicki/sim/diagnostics.py tests/sim/test_diagnostics.py
git commit -m "$(cat <<'EOF'
feat(sim): observed insertion angles in diagnostics

Adds insertion_angle_deg_vs_parent and
insertion_angle_deg_vs_main_sibling per child axis_order. Tangents
computed from topological geometry (ignoring sag_offset). Covers
spec tests #4–#5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Divergence-angle metric

**Goal:** `divergence_angle_deg` populated by walking axis chains and computing consecutive azimuth deltas.

**Files:**
- Modify: `src/palubicki/sim/diagnostics.py`
- Modify: `tests/sim/test_diagnostics.py`

- [ ] **Step 3.1: Write test #6 — two laterals at known azimuths.**

```python
# Append to tests/sim/test_diagnostics.py

def test_divergence_angle_known_pair():
    """Trunk +Y, two main-axis continuations along +Y. At each continuation's
    child node, one lateral. Lateral 1 points along +X (azimuth 0°);
    lateral 2 points at azimuth 137.5° in the XZ plane → divergence = 137.5°.
    """
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    n1 = Node(position=np.array([0.0, 1.0, 0.0]))
    n2 = Node(position=np.array([0.0, 2.0, 0.0]))
    # Phyllotaxy's _frame_perpendicular_to(+Y) yields right=+X, up=-Z (Gram-
    # Schmidt against canonical=+X). To make azimuth 0° → +X, the lateral
    # tangent must lie purely along +X in the (right=+X, up=-Z) plane.
    # That is, lateral 1 direction = +X with some +Y component is fine
    # because the azimuth is computed in the perpendicular plane only.
    az2_rad = math.radians(137.5)
    # In phyllotaxy's basis (right=+X, up=-Z), azimuth θ → cos(θ)*X + sin(θ)*(-Z)
    lat1_dir = np.array([1.0, 0.5, 0.0])  # purely +X in XZ plane
    lat2_dir = np.array([math.cos(az2_rad), 0.5, -math.sin(az2_rad)])

    lat1_node = Node(position=n1.position + lat1_dir)
    lat2_node = Node(position=n2.position + lat2_dir)

    tree = Tree(root=root)
    trunk = _link(root, n1, axis_order=0, is_main_axis=True)
    cont = _link(n1, n2, axis_order=0, is_main_axis=True)
    l1 = _link(n1, lat1_node, axis_order=1, is_main_axis=False)
    l2 = _link(n2, lat2_node, axis_order=1, is_main_axis=False)
    tree.all_internodes.extend([trunk, cont, l1, l2])

    m = compute_metrics(tree)
    assert 1 in m["divergence_angle_deg"]
    stats = m["divergence_angle_deg"][1]
    assert stats["mean"] == pytest.approx(137.5, abs=0.5)
    assert stats["n"] == 1
```

- [ ] **Step 3.2: Run the test, confirm `KeyError`.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py::test_divergence_angle_known_pair -v`
Expected: FAIL.

- [ ] **Step 3.3: Implement axis-chain walker and divergence helper.**

Append to `src/palubicki/sim/diagnostics.py` (after `_insertion_angle_metrics`):

```python
# ── Axis chains and divergence ────────────────────────────────────────────

def _walk_axis_chains(root: Node) -> list[list[Internode]]:
    """Return list of chains. Each chain = maximal sequence of internodes
    sharing one axis_order, linked by is_main_axis-true continuation.

    A chain starts at an internode L where either:
      - L.parent_node has no incoming internode (the trunk's first segment),
      - L.parent_node.parent_internode.axis_order != L.axis_order (L is a
        lateral that begins a new axis).
    """
    chains: list[list[Internode]] = []
    visited: set[int] = set()

    for iod in _walk_internodes(root):
        if id(iod) in visited:
            continue
        incoming = iod.parent_node.parent_internode
        if incoming is not None and incoming.axis_order == iod.axis_order:
            continue  # main-axis continuation of an already-walked chain
        # Start a new chain.
        chain: list[Internode] = [iod]
        visited.add(id(iod))
        cur = iod
        while True:
            nxt: Internode | None = None
            for c in cur.child_node.children_internodes:
                if c.axis_order == cur.axis_order:
                    # Main-axis continuation: same order, same chain.
                    nxt = c
                    break
            if nxt is None:
                break
            chain.append(nxt)
            visited.add(id(nxt))
            cur = nxt
        chains.append(chain)
    return chains


def _frame_perpendicular_to(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Duplicated from sim/phyllotaxy.py for in-plane basis consistency.

    Both implementations MUST stay in sync: phyllotaxy uses this basis to
    place lateral buds, and the diagnostics harness measures their observed
    divergence in the same basis. If you change one, change both.
    """
    canonical = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    right = canonical - np.dot(canonical, d) * d
    right = right / np.linalg.norm(right)
    up = np.cross(d, right)
    return right, up


def _divergence_angle_metrics(chains: list[list[Internode]]) -> dict:
    """For each chain, walk in order. At each chain internode, collect its
    lateral children (children at chain[i].child_node whose axis_order
    differs from the chain order). For each consecutive lateral pair,
    compute azimuth difference mod 360° in the basis perpendicular to the
    chain tangent at that point. Group by the lateral's axis_order.
    """
    by_order: dict[int, list[float]] = defaultdict(list)

    for chain in chains:
        laterals: list[tuple[Internode, Internode]] = []  # (chain_iod, lateral_iod)
        for cur in chain:
            for c in cur.child_node.children_internodes:
                if c.axis_order != cur.axis_order:
                    laterals.append((cur, c))
        if len(laterals) < 2:
            continue

        prev_az: float | None = None
        for cur, lat in laterals:
            T = _tangent(cur)
            right, up = _frame_perpendicular_to(T)
            lat_t = _tangent(lat)
            az = math.degrees(math.atan2(float(np.dot(lat_t, up)),
                                          float(np.dot(lat_t, right))))
            if prev_az is not None:
                diff = (az - prev_az) % 360.0
                by_order[lat.axis_order].append(diff)
            prev_az = az

    return {"divergence_angle_deg": {k: _stats(v) for k, v in by_order.items()}}
```

Update `compute_metrics` to call the new helper:

```python
def compute_metrics(
    tree: "Tree | list[Tree]",
    *,
    cfg: "Config | None" = None,
) -> dict:
    if isinstance(tree, list):
        raise NotImplementedError("multi-seed compute_metrics arrives in Task 7")

    internodes = _walk_internodes(tree.root)
    chains = _walk_axis_chains(tree.root)
    out: dict = {}
    out.update(_strahler_metrics(tree.root))
    out.update(_insertion_angle_metrics(internodes))
    out.update(_divergence_angle_metrics(chains))
    return out
```

- [ ] **Step 3.4: Run the test, confirm pass.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py::test_divergence_angle_known_pair -v`
Expected: PASS.

- [ ] **Step 3.5: Add a sanity test — single-lateral axis contributes nothing.**

```python
# Append to tests/sim/test_diagnostics.py

def test_divergence_angle_single_lateral_contributes_nothing():
    tree = _make_trunk_with_lateral(branch_dir=np.array([1.0, 1.0, 0.0]))
    m = compute_metrics(tree)
    # One lateral on one axis → no divergence pairs at all.
    assert m["divergence_angle_deg"] == {}
```

- [ ] **Step 3.6: Run, confirm pass; run the whole diagnostics test file.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -v`
Expected: all PASS (≥ 7 tests).

- [ ] **Step 3.7: Commit.**

```bash
git add src/palubicki/sim/diagnostics.py tests/sim/test_diagnostics.py
git commit -m "$(cat <<'EOF'
feat(sim): observed divergence angle per axis order

Walks each axis chain (same-axis_order internodes linked by
is_main_axis), collects consecutive lateral children, and reports
their azimuth differences in the same perpendicular basis used by
sim/phyllotaxy.py. Covers spec test #6.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Counts + architecture metrics

**Goal:** Add `sympodial_fork_count`, `bud_state_histogram`, `tree_height`, `trunk_base_diameter`, `crown_radius` to the dict.

**Files:**
- Modify: `src/palubicki/sim/diagnostics.py`
- Modify: `tests/sim/test_diagnostics.py`

- [ ] **Step 4.1: Write test #7 — bud histogram walks all nodes.**

```python
# Append to tests/sim/test_diagnostics.py

from palubicki.sim.tree import Bud  # add near other tree imports


def test_bud_state_histogram_walks_all_nodes():
    """A DORMANT bud on a non-active-list node must be counted."""
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    child = Node(position=np.array([0.0, 1.0, 0.0]))
    tree = Tree(root=root)
    iod = _link(root, child, axis_order=0, is_main_axis=True)
    tree.all_internodes.append(iod)

    # Active terminal at the child.
    term = Bud(position=child.position, direction=np.array([0.0, 1.0, 0.0]),
               axis_order=0, parent_node=child)
    child.terminal_bud = term
    tree.active_buds.append(term)

    # Dormant lateral at the child — NOT in tree.active_buds.
    dormant = Bud(position=child.position, direction=np.array([1.0, 0.0, 0.0]),
                  axis_order=1, parent_node=child)
    dormant.state = BudState.DORMANT
    child.lateral_buds.append(dormant)

    # Reserve at the root.
    reserve = Bud(position=root.position, direction=np.array([0.0, 0.0, 1.0]),
                  axis_order=0, parent_node=root)
    reserve.state = BudState.RESERVE
    root.dormant_reserve_buds.append(reserve)

    m = compute_metrics(tree)
    hist = m["bud_state_histogram"]
    assert hist["ACTIVE"] == 1
    assert hist["DORMANT"] == 1
    assert hist["RESERVE"] == 1
    assert hist.get("DEAD", 0) == 0
```

- [ ] **Step 4.2: Run, confirm `KeyError`.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py::test_bud_state_histogram_walks_all_nodes -v`
Expected: FAIL.

- [ ] **Step 4.3: Implement counts + architecture helpers.**

Append to `src/palubicki/sim/diagnostics.py`:

```python
# ── Counts ────────────────────────────────────────────────────────────────

def _bud_state_histogram(nodes: list[Node]) -> dict[str, int]:
    counts: dict[str, int] = {s.name: 0 for s in BudState}
    for n in nodes:
        if n.terminal_bud is not None:
            counts[n.terminal_bud.state.name] += 1
        for b in n.lateral_buds:
            counts[b.state.name] += 1
        for b in n.dormant_reserve_buds:
            counts[b.state.name] += 1
    return counts


def _sympodial_fork_count(nodes: list[Node]) -> int:
    return sum(1 for n in nodes if n.sympodial_fork)


# ── Architecture ──────────────────────────────────────────────────────────

def _height_and_crown(nodes: list[Node]) -> tuple[float, float]:
    """Returns (tree_height, crown_radius).

    tree_height = max((position + sag_offset)[1]).
    crown_radius = max sqrt(x² + z²) over bent positions with y > 0.4*height.
    Root-only tree → (root.position[1], 0.0).
    """
    if not nodes:
        return (0.0, 0.0)
    ys = [float((n.position + n.sag_offset)[1]) for n in nodes]
    height = max(ys)
    threshold = 0.4 * height
    crown = 0.0
    for n in nodes:
        bent = n.position + n.sag_offset
        if float(bent[1]) > threshold:
            r = float(math.hypot(bent[0], bent[2]))
            if r > crown:
                crown = r
    return (height, crown)


def _trunk_base_diameter(root: Node) -> float:
    if not root.children_internodes:
        return 0.0
    return max(float(iod.diameter) for iod in root.children_internodes)
```

Update `compute_metrics`:

```python
def compute_metrics(
    tree: "Tree | list[Tree]",
    *,
    cfg: "Config | None" = None,
) -> dict:
    if isinstance(tree, list):
        raise NotImplementedError("multi-seed compute_metrics arrives in Task 7")

    nodes = _walk_nodes(tree.root)
    internodes = _walk_internodes(tree.root)
    chains = _walk_axis_chains(tree.root)

    height, crown_radius = _height_and_crown(nodes)

    out: dict = {}
    out.update(_strahler_metrics(tree.root))
    out.update(_insertion_angle_metrics(internodes))
    out.update(_divergence_angle_metrics(chains))
    out["sympodial_fork_count"] = _sympodial_fork_count(nodes)
    out["bud_state_histogram"] = _bud_state_histogram(nodes)
    out["tree_height"] = height
    out["trunk_base_diameter"] = _trunk_base_diameter(tree.root)
    out["crown_radius"] = crown_radius
    out["total_leaf_area"] = 0.0  # populated in Task 6
    return out
```

- [ ] **Step 4.4: Run the bud-histogram test, confirm pass.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py::test_bud_state_histogram_walks_all_nodes -v`
Expected: PASS.

- [ ] **Step 4.5: Add tests #8, #9, #10.**

```python
# Append to tests/sim/test_diagnostics.py

def test_sympodial_count_uses_node_flag():
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    a = Node(position=np.array([0.0, 1.0, 0.0]))
    b = Node(position=np.array([0.0, 2.0, 0.0]))
    a.sympodial_fork = True
    b.sympodial_fork = True
    tree = Tree(root=root)
    i1 = _link(root, a, axis_order=0, is_main_axis=True)
    i2 = _link(a, b, axis_order=0, is_main_axis=True)
    tree.all_internodes.extend([i1, i2])

    m = compute_metrics(tree)
    assert m["sympodial_fork_count"] == 2


def test_height_uses_sag_offset():
    """Node positioned at y=5 with sag_offset y=-0.4 → tree_height = 4.6."""
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    top = Node(position=np.array([0.0, 5.0, 0.0]))
    top.sag_offset = np.array([0.0, -0.4, 0.0])
    tree = Tree(root=root)
    iod = _link(root, top, axis_order=0, is_main_axis=True)
    tree.all_internodes.append(iod)

    m = compute_metrics(tree)
    assert m["tree_height"] == pytest.approx(4.6, abs=1e-9)


def test_crown_radius_band_only():
    """Wide low node (y=0.5, below 0.4*height) is ignored.
    Narrower high node (y=4.0) defines crown_radius.
    """
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    low_wide = Node(position=np.array([3.0, 0.5, 0.0]))  # r=3, but below band
    mid = Node(position=np.array([0.0, 2.0, 0.0]))
    high_narrow = Node(position=np.array([1.5, 4.0, 0.0]))  # r=1.5, in band
    top = Node(position=np.array([0.0, 5.0, 0.0]))         # tree_height = 5
    tree = Tree(root=root)
    tree.all_internodes.append(_link(root, low_wide, axis_order=1,
                                      is_main_axis=False))
    tree.all_internodes.append(_link(root, mid, axis_order=0, is_main_axis=True))
    tree.all_internodes.append(_link(mid, high_narrow, axis_order=1,
                                      is_main_axis=False))
    tree.all_internodes.append(_link(mid, top, axis_order=0, is_main_axis=True))

    m = compute_metrics(tree)
    # 0.4 * 5.0 = 2.0; nodes with y > 2.0 are high_narrow (y=4) and top (y=5).
    # high_narrow has r=1.5; top has r=0. Crown = 1.5.
    assert m["tree_height"] == pytest.approx(5.0)
    assert m["crown_radius"] == pytest.approx(1.5, abs=1e-9)


def test_trunk_base_diameter():
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    top = Node(position=np.array([0.0, 1.0, 0.0]))
    tree = Tree(root=root)
    iod = _link(root, top, axis_order=0, is_main_axis=True)
    iod.diameter = 0.18
    tree.all_internodes.append(iod)
    m = compute_metrics(tree)
    assert m["trunk_base_diameter"] == pytest.approx(0.18)


def test_root_only_tree_returns_zeros():
    """Degenerate single-node tree must not crash."""
    root = Node(position=np.array([0.0, 0.0, 0.0]))
    tree = Tree(root=root)
    m = compute_metrics(tree)
    assert m["strahler_order_max"] == 0
    assert m["sympodial_fork_count"] == 0
    assert m["tree_height"] == pytest.approx(0.0)
    assert m["trunk_base_diameter"] == pytest.approx(0.0)
    assert m["crown_radius"] == pytest.approx(0.0)
    assert m["total_leaf_area"] == pytest.approx(0.0)
```

- [ ] **Step 4.6: Run all diagnostics tests, confirm pass.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -v`
Expected: all PASS.

- [ ] **Step 4.7: Commit.**

```bash
git add src/palubicki/sim/diagnostics.py tests/sim/test_diagnostics.py
git commit -m "$(cat <<'EOF'
feat(sim): bud histogram, sympodial count, height/crown/base diameter

Bud histogram walks all nodes (not tree.active_buds, which would
undercount DORMANT/DEAD/RESERVE). Height uses bent positions to
match rendered output. Crown radius limited to nodes with
y > 0.4*height. Covers spec tests #7–#10 plus root-only smoke test.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Extract `compute_effective_leaf_size` (refactor C)

**Goal:** Single source of truth for sun/shade leaf scaling between the renderer (`build_leaves_primitive`) and the diagnostics harness. `geom/leaves.py` exposes a new public helper; the existing renderer calls it. The .glb output is bit-identical before and after.

**Files:**
- Modify: `src/palubicki/geom/leaves.py`
- Modify: `tests/sim/test_diagnostics.py`

- [ ] **Step 5.1: Capture baseline leaves-primitive positions for parity test (test #15).**

Append to `tests/sim/test_diagnostics.py`:

```python
# Add to existing imports at the top of the file:
#   from palubicki.config import load_config
#   from palubicki.geom.leaves import build_leaves_primitive
#   from palubicki.sim.simulator import simulate
#   from pathlib import Path

@pytest.mark.slow
def test_compute_effective_leaf_size_extraction_preserves_geom_output():
    """Refactor invariant: build_leaves_primitive(...) must produce the
    same positions array before and after the C extraction. We bake the
    expected positions from a fixed seed/species and assert equality on
    re-run."""
    from palubicki.config import load_config
    from palubicki.geom.leaves import build_leaves_primitive
    from palubicki.geom.mesh import Material
    from palubicki.sim.simulator import simulate

    cfg = load_config(yaml_path=None, cli_overrides={"seed": 0},
                      output=Path("tree.glb"), species="oak")
    tree = simulate(cfg)

    g = cfg.geom
    mat = Material(name="leaves_a", base_color_rgba=(0.2, 0.6, 0.2, 1.0),
                   double_sided=True, alpha_mode="OPAQUE")
    prim = build_leaves_primitive(
        tree,
        leaf_size=g.leaf_size,
        material=mat,
        cluster_count=g.leaf_cluster_count,
        aspect=g.leaf_aspect,
        splay_deg=g.leaf_splay_deg,
        foliage_depth=g.foliage_depth,
        sun_shade_k=g.leaf_sun_shade_k,
    )
    # We don't have a pre-refactor snapshot — this test guards against
    # FUTURE drift, so we just sanity-check shape and finiteness here,
    # then keep the same call site green after the extraction.
    assert prim.positions.shape[1] == 3
    assert np.all(np.isfinite(prim.positions))
    # Stash a hash for stable cross-refactor comparison.
    h = float(np.sum(prim.positions ** 2))
    assert h > 0.0
```

The parity guarantee is the easy direction (the test runs both before and after the refactor; if anything changes, the positions hash drifts and the *next* run of the test gives a different value — but pytest can't see the previous value). To make the parity test load-bearing, **capture the hash now** then assert against it after extraction. Step 5.2 does the capture; Step 5.4 hard-codes the value into the assertion.

- [ ] **Step 5.2: Run the test to capture the pre-refactor hash.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py::test_compute_effective_leaf_size_extraction_preserves_geom_output -v -s`

Modify the test inline to print the hash, then re-run, copy the printed value (a number like `1234.5678901234`), and remove the print. Replace the final assertion in the test with:

```python
    # Hash captured pre-refactor; must remain identical after extraction.
    h = float(np.sum(prim.positions ** 2))
    assert h == pytest.approx(<PASTE_HASH_HERE>, rel=0, abs=1e-9)
```

Replace `<PASTE_HASH_HERE>` with the value you observed.

- [ ] **Step 5.3: Refactor `geom/leaves.py` — extract the helper.**

Open `src/palubicki/geom/leaves.py`. After the imports and before `build_leaves_primitive`, add:

```python
def compute_effective_leaf_size(
    internode: "Internode | None",
    leaf_size: float,
    sun_shade_k: float,
) -> float:
    """Effective per-site leaf edge length under sun/shade scaling.

    Shared between the renderer (build_leaves_primitive) and the
    diagnostics harness so leaf-area accounting cannot drift from
    what the .glb actually contains.

    Sites with no source_internode (root apex) use light_factor=1.0,
    matching the renderer's existing fallback.
    """
    lf = internode.light_factor if internode is not None else 1.0
    if sun_shade_k > 0.0:
        eff = leaf_size * (1.0 + sun_shade_k * (1.0 - lf))
        return max(0.5 * leaf_size, min(2.0 * leaf_size, eff))
    return leaf_size
```

Then edit `build_leaves_primitive` (around lines 53–63 of the current file) — replace the body of the loop that computes `eff_size`:

Before:
```python
    splay_rad = math.radians(splay_deg)
    min_size = 0.5 * leaf_size
    max_size = 2.0 * leaf_size

    for i, (center, direction, source_iod) in enumerate(sites):
        lf = source_iod.light_factor if source_iod is not None else 1.0
        if sun_shade_k > 0.0:
            eff_size = leaf_size * (1.0 + sun_shade_k * (1.0 - lf))
            eff_size = max(min_size, min(max_size, eff_size))
        else:
            eff_size = leaf_size
```

After:
```python
    splay_rad = math.radians(splay_deg)

    for i, (center, direction, source_iod) in enumerate(sites):
        eff_size = compute_effective_leaf_size(source_iod, leaf_size, sun_shade_k)
```

(The `min_size` / `max_size` locals are dropped — they only existed for the inline clamp.)

- [ ] **Step 5.4: Run the parity test, confirm pass (hash unchanged).**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py::test_compute_effective_leaf_size_extraction_preserves_geom_output -v`
Expected: PASS. If FAIL, the extraction changed behaviour — diff the math, fix.

- [ ] **Step 5.5: Run the full geom test suite for safety.**

Run: `.venv/bin/pytest tests/geom -v`
Expected: all PASS (or the pre-existing baseline; no new failures).

- [ ] **Step 5.6: Commit.**

```bash
git add src/palubicki/geom/leaves.py tests/sim/test_diagnostics.py
git commit -m "$(cat <<'EOF'
refactor(geom): extract compute_effective_leaf_size

Pulls the sun/shade leaf-scaling math out of build_leaves_primitive
into a public helper so the upcoming diagnostics harness can compute
leaf area from the exact same formula the renderer uses. Behaviour
of the .glb output is unchanged (parity test hash-checks the
positions array).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `total_leaf_area` metric

**Goal:** `compute_metrics(tree, cfg=cfg)["total_leaf_area"]` matches summed quad areas from `build_leaves_primitive`.

**Files:**
- Modify: `src/palubicki/sim/diagnostics.py`
- Modify: `tests/sim/test_diagnostics.py`

- [ ] **Step 6.1: Write test #11 — leaf area matches summed quad areas.**

```python
# Append to tests/sim/test_diagnostics.py

@pytest.mark.slow
def test_leaf_area_matches_geom_helper():
    """Cross-check: compute total_leaf_area via the diagnostics harness, and
    independently sum quad areas from the rendered positions array. Must
    match to within float epsilon."""
    from palubicki.config import load_config
    from palubicki.geom.leaves import build_leaves_primitive
    from palubicki.geom.mesh import Material
    from palubicki.sim.simulator import simulate

    cfg = load_config(yaml_path=None, cli_overrides={"seed": 0},
                      output=Path("tree.glb"), species="oak")
    tree = simulate(cfg)

    g = cfg.geom
    mat = Material(name="leaves_a", base_color_rgba=(0.2, 0.6, 0.2, 1.0),
                   double_sided=True, alpha_mode="OPAQUE")
    prim = build_leaves_primitive(
        tree,
        leaf_size=g.leaf_size,
        material=mat,
        cluster_count=g.leaf_cluster_count,
        aspect=g.leaf_aspect,
        splay_deg=g.leaf_splay_deg,
        foliage_depth=g.foliage_depth,
        sun_shade_k=g.leaf_sun_shade_k,
    )

    # Sum quad areas directly from positions. Each indexed triangle:
    # 0.5 * |edge1 × edge2|. Iterate over indices in triplets.
    pos = prim.positions
    idx = prim.indices.reshape(-1, 3)
    e1 = pos[idx[:, 1]] - pos[idx[:, 0]]
    e2 = pos[idx[:, 2]] - pos[idx[:, 0]]
    tri_areas = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    rendered_area = float(tri_areas.sum())

    m = compute_metrics(tree, cfg=cfg)
    assert m["total_leaf_area"] == pytest.approx(rendered_area, rel=1e-5)
```

- [ ] **Step 6.2: Run, confirm fail (`total_leaf_area` is still hard-coded to 0).**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py::test_leaf_area_matches_geom_helper -v`
Expected: FAIL.

- [ ] **Step 6.3: Implement `_total_leaf_area` and wire it in.**

Append to `src/palubicki/sim/diagnostics.py`:

```python
# ── Leaf area ─────────────────────────────────────────────────────────────

def _total_leaf_area(tree: Tree, cfg: "Config") -> float:
    """Sum of rendered leaf surface areas across foliage sites.

    Per site, area = 2 * cluster_count * eff_size² * aspect:
      - 2 quads per cluster (cross-quad: u-plane and w-plane),
      - cluster_count clusters,
      - each quad is (eff_size * aspect) wide by eff_size tall.
    """
    from palubicki.geom.leaves import _collect_foliage_sites, compute_effective_leaf_size

    g = cfg.geom
    sites = _collect_foliage_sites(tree, g.foliage_depth)
    if not sites:
        return 0.0
    total = 0.0
    for _center, _direction, source_iod in sites:
        eff = compute_effective_leaf_size(source_iod, g.leaf_size, g.leaf_sun_shade_k)
        total += 2.0 * g.leaf_cluster_count * (eff * eff) * g.leaf_aspect
    return total
```

Update `compute_metrics` — replace the `out["total_leaf_area"] = 0.0` line with:

```python
    if cfg is not None:
        out["total_leaf_area"] = _total_leaf_area(tree, cfg)
    else:
        out["total_leaf_area"] = 0.0
```

- [ ] **Step 6.4: Run, confirm the parity test passes.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py::test_leaf_area_matches_geom_helper -v`
Expected: PASS.

- [ ] **Step 6.5: Run the full diagnostics suite for regressions.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -v`
Expected: all PASS.

- [ ] **Step 6.6: Commit.**

```bash
git add src/palubicki/sim/diagnostics.py tests/sim/test_diagnostics.py
git commit -m "$(cat <<'EOF'
feat(sim): total_leaf_area in diagnostics dict

Walks _collect_foliage_sites and sums (2 × cluster_count × eff_size²
× aspect) per site. Cross-check test confirms agreement with the
summed quad areas from build_leaves_primitive's rendered positions.
Covers spec test #11.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Multi-seed aggregation

**Goal:** `compute_metrics([t1, t2, ...])` returns a dict whose scalar leaves wrap into `{mean, stddev, per_seed}`. Per-order dicts wrap key-by-key.

**Files:**
- Modify: `src/palubicki/sim/diagnostics.py`
- Modify: `tests/sim/test_diagnostics.py`

- [ ] **Step 7.1: Write test #12 — multi-seed aggregation, hand-built.**

```python
# Append to tests/sim/test_diagnostics.py

def test_compute_metrics_accepts_list_of_trees():
    """Two hand-built trees with known heights → mean/stddev/per_seed."""
    def trunk_to_height(h: float) -> Tree:
        root = Node(position=np.array([0.0, 0.0, 0.0]))
        top = Node(position=np.array([0.0, h, 0.0]))
        tree = Tree(root=root)
        iod = _link(root, top, axis_order=0, is_main_axis=True)
        tree.all_internodes.append(iod)
        return tree

    t1 = trunk_to_height(2.0)
    t2 = trunk_to_height(4.0)
    m = compute_metrics([t1, t2])

    h = m["tree_height"]
    assert h["mean"] == pytest.approx(3.0)
    assert h["stddev"] == pytest.approx(1.0)  # population stddev of [2,4]
    assert h["per_seed"] == [pytest.approx(2.0), pytest.approx(4.0)]

    # Strahler histogram aggregates key-by-key.
    hist = m["strahler_order_histogram"]
    assert hist[1]["mean"] == pytest.approx(1.0)
    assert hist[1]["per_seed"] == [1, 1]


def test_compute_metrics_multi_seed_missing_axis_order():
    """One tree has order-2 internodes, the other doesn't.

    The order-1 angle stats appear in both → fully populated.
    The order-2 entries only appear in tree #1 → per_seed = [val, None],
    mean/stddev computed over non-None.
    """
    # Tree A: trunk + lateral (axis_order=1) + lateral-of-lateral (axis_order=2)
    rootA = Node(position=np.array([0.0, 0.0, 0.0]))
    midA = Node(position=np.array([0.0, 1.0, 0.0]))
    latA = Node(position=np.array([1.0, 1.5, 0.0]))
    sublatA = Node(position=np.array([1.5, 2.0, 0.0]))
    treeA = Tree(root=rootA)
    treeA.all_internodes.extend([
        _link(rootA, midA, axis_order=0, is_main_axis=True),
        _link(midA, latA, axis_order=1, is_main_axis=False),
        _link(latA, sublatA, axis_order=2, is_main_axis=False),
    ])
    # Tree B: trunk + lateral only (no axis_order=2 internode).
    rootB = Node(position=np.array([0.0, 0.0, 0.0]))
    midB = Node(position=np.array([0.0, 1.0, 0.0]))
    latB = Node(position=np.array([1.0, 1.5, 0.0]))
    treeB = Tree(root=rootB)
    treeB.all_internodes.extend([
        _link(rootB, midB, axis_order=0, is_main_axis=True),
        _link(midB, latB, axis_order=1, is_main_axis=False),
    ])

    m = compute_metrics([treeA, treeB])
    # Order-1 vs_parent is populated in both — both should have stats.
    assert 1 in m["insertion_angle_deg_vs_parent"]
    # Order-2 only exists in A. Aggregate should still expose it.
    assert 2 in m["insertion_angle_deg_vs_parent"]
    o2 = m["insertion_angle_deg_vs_parent"][2]
    assert "mean" in o2
    # Per-seed list has None for tree B.
    assert o2["per_seed"][1] is None
```

- [ ] **Step 7.2: Run, confirm `NotImplementedError`.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py::test_compute_metrics_accepts_list_of_trees -v`
Expected: FAIL with NotImplementedError.

- [ ] **Step 7.3: Implement multi-seed aggregation.**

Replace the `if isinstance(tree, list):` branch in `compute_metrics`:

```python
def compute_metrics(
    tree: "Tree | list[Tree]",
    *,
    cfg: "Config | None" = None,
) -> dict:
    if isinstance(tree, list):
        per_tree = [compute_metrics(t, cfg=cfg) for t in tree]
        return _aggregate(per_tree)
    # … rest unchanged …
```

Add the `_aggregate` helper near the end of the file:

```python
# ── Multi-seed aggregation ────────────────────────────────────────────────

def _aggregate(per_tree: list[dict]) -> dict:
    """Combine N per-tree metric dicts into a single dict where each scalar
    leaf becomes {mean, stddev, per_seed} and each angle-stats sub-dict is
    wrapped key-by-key.

    For per-order keys (insertion / divergence): the union of axis orders
    across trees is taken; trees missing an order contribute `None` to
    per_seed, and mean/stddev are computed over the non-None subset.
    For histogram keys (Strahler order, bud state): the union of bins is
    taken; missing bins are treated as 0.
    """
    if not per_tree:
        return {}

    # Identify keys by inspecting the first dict.
    sample = per_tree[0]
    out: dict = {}

    # Scalar keys.
    SCALAR_KEYS = (
        "strahler_order_max",
        "horton_bifurcation_ratio_mean",
        "sympodial_fork_count",
        "tree_height",
        "trunk_base_diameter",
        "crown_radius",
        "total_leaf_area",
    )
    for k in SCALAR_KEYS:
        vals = [m[k] for m in per_tree]
        out[k] = _agg_scalar(vals)

    # Histogram-style dicts (treat missing keys as 0).
    HIST_KEYS = ("strahler_order_histogram", "bud_state_histogram")
    for k in HIST_KEYS:
        all_keys: set = set()
        for m in per_tree:
            all_keys.update(m[k].keys())
        out[k] = {
            kk: _agg_scalar([m[k].get(kk, 0) for m in per_tree])
            for kk in sorted(all_keys, key=lambda x: (isinstance(x, str), x))
        }

    # horton_bifurcation_ratio: keyed by order N (treat missing as None).
    out["horton_bifurcation_ratio"] = _agg_optional_dict(per_tree, "horton_bifurcation_ratio")

    # Angle-stats per-order dicts (insertion_*, divergence_*).
    # Each per-tree value at [order] is {"mean", "stddev", "n"}. Aggregate the
    # "mean" across trees; the "n" gets summed (or kept as None when missing).
    for k in ("insertion_angle_deg_vs_parent",
              "insertion_angle_deg_vs_main_sibling",
              "divergence_angle_deg"):
        all_orders: set = set()
        for m in per_tree:
            all_orders.update(m[k].keys())
        agg: dict = {}
        for order in sorted(all_orders):
            means: list = [m[k].get(order, {}).get("mean") if order in m[k] else None
                           for m in per_tree]
            agg[order] = _agg_scalar(means)
        out[k] = agg
    return out


def _agg_scalar(values: list) -> dict:
    """Aggregate a list of scalars (with None for missing). Returns
    {mean, stddev, per_seed}."""
    non_null = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not non_null:
        return {"mean": float("nan"), "stddev": float("nan"), "per_seed": values}
    arr = np.asarray(non_null, dtype=np.float64)
    return {
        "mean": float(arr.mean()),
        "stddev": float(arr.std(ddof=0)),
        "per_seed": values,
    }


def _agg_optional_dict(per_tree: list[dict], key: str) -> dict:
    all_keys: set = set()
    for m in per_tree:
        all_keys.update(m[key].keys())
    out: dict = {}
    for kk in sorted(all_keys):
        out[kk] = _agg_scalar([m[key].get(kk) for m in per_tree])
    return out
```

- [ ] **Step 7.4: Run the multi-seed tests, confirm pass.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -v -k "list_of_trees or missing_axis_order"`
Expected: 2 PASS.

- [ ] **Step 7.5: Run the full diagnostics suite.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -v`
Expected: all PASS.

- [ ] **Step 7.6: Commit.**

```bash
git add src/palubicki/sim/diagnostics.py tests/sim/test_diagnostics.py
git commit -m "$(cat <<'EOF'
feat(sim): multi-seed aggregation in compute_metrics

compute_metrics([t1, t2, ...]) recurses per-tree and wraps each
scalar / per-order entry into {mean, stddev, per_seed} with None
placeholders for axis orders absent from some seeds. Histograms
union over bin keys. Covers spec test #12.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `MetricRanges` + `format_report`

**Goal:** Pretty-printed report layout (single-seed + multi-seed) with ✓/✗ flags driven by `MetricRanges`.

**Files:**
- Modify: `src/palubicki/sim/diagnostics.py`
- Modify: `tests/sim/test_diagnostics.py`

- [ ] **Step 8.1: Write a format_report flag-detection test.**

```python
# Append to tests/sim/test_diagnostics.py

def test_format_report_single_seed_includes_keys_and_flag():
    from palubicki.sim.diagnostics import format_report

    metrics = {
        "strahler_order_max": 4,
        "strahler_order_histogram": {1: 78, 2: 18, 3: 5, 4: 1},
        "horton_bifurcation_ratio": {1: 4.33, 2: 3.60, 3: 5.00},
        "horton_bifurcation_ratio_mean": 4.27,
        "insertion_angle_deg_vs_parent": {
            1: {"mean": 52.1, "stddev": 6.4, "n": 18},
        },
        "insertion_angle_deg_vs_main_sibling": {},
        "divergence_angle_deg": {
            1: {"mean": 137.4, "stddev": 9.2, "n": 12},
        },
        "sympodial_fork_count": 3,
        "bud_state_histogram": {"ACTIVE": 24, "DORMANT": 7, "DEAD": 12, "RESERVE": 5},
        "tree_height": 5.42,
        "trunk_base_diameter": 0.18,
        "crown_radius": 2.91,
        "total_leaf_area": 12.4,
    }
    out = format_report(metrics, seeds=[0], species="oak")
    assert "tree_height" in out
    assert "bifurcation_ratio" in out or "bif_ratio" in out
    assert "✓" in out  # bif_ratio_mean=4.27 is in [3.0, 5.0]


def test_format_report_multi_seed_has_mean_stddev():
    from palubicki.sim.diagnostics import format_report

    # Synthesize multi-seed-shaped dict directly (no need to re-run
    # compute_metrics here).
    multi = {
        "strahler_order_max": {"mean": 4.0, "stddev": 0.0, "per_seed": [4, 4]},
        "strahler_order_histogram": {1: {"mean": 78.0, "stddev": 0.0, "per_seed": [78, 78]}},
        "horton_bifurcation_ratio": {},
        "horton_bifurcation_ratio_mean": {"mean": 4.18, "stddev": 0.41, "per_seed": [4.0, 4.36]},
        "insertion_angle_deg_vs_parent": {1: {"mean": 51.7, "stddev": 1.2, "per_seed": [50.5, 52.9]}},
        "insertion_angle_deg_vs_main_sibling": {},
        "divergence_angle_deg": {1: {"mean": 136.9, "stddev": 2.3, "per_seed": [135.0, 138.8]}},
        "sympodial_fork_count": {"mean": 3.4, "stddev": 1.1, "per_seed": [2, 5]},
        "bud_state_histogram": {"DEAD": {"mean": 11.6, "stddev": 2.1, "per_seed": [10, 13]}},
        "tree_height": {"mean": 5.31, "stddev": 0.18, "per_seed": [5.13, 5.49]},
        "trunk_base_diameter": {"mean": 0.17, "stddev": 0.01, "per_seed": [0.16, 0.18]},
        "crown_radius": {"mean": 2.84, "stddev": 0.21, "per_seed": [2.6, 3.0]},
        "total_leaf_area": {"mean": 11.9, "stddev": 0.8, "per_seed": [11.1, 12.7]},
    }
    out = format_report(multi, seeds=[0, 1], species="oak")
    assert "mean" in out
    assert "stddev" in out
    assert "✓" in out  # bif_ratio_mean=4.18 still in range
```

- [ ] **Step 8.2: Run, confirm `ImportError`.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -v -k format_report`
Expected: FAIL (ImportError).

- [ ] **Step 8.3: Implement `MetricRanges` and `format_report`.**

Append to `src/palubicki/sim/diagnostics.py`:

```python
# ── Reference-range flags and pretty-printer ──────────────────────────────

@dataclass
class MetricRanges:
    """Literature-range bounds for ✓/✗ flagging.

    Field names follow the spec's path convention:
      "horton_bifurcation_ratio_mean"
        → metrics["horton_bifurcation_ratio_mean"]
      "divergence_angle_deg__orderN_mean"
        → metrics["divergence_angle_deg"][N]["mean"]
      "insertion_angle_deg_vs_parent__orderN_mean"
        → metrics["insertion_angle_deg_vs_parent"][N]["mean"]
    Missing field = no flag rendered for that metric.
    """
    horton_bifurcation_ratio_mean: tuple[float, float] = (3.0, 5.0)
    divergence_angle_deg__order1_mean: tuple[float, float] = (130.0, 145.0)
    insertion_angle_deg_vs_parent__order1_mean: tuple[float, float] = (30.0, 65.0)


DEFAULT_RANGES = MetricRanges()


def _flag(value: float | None, bounds: tuple[float, float] | None) -> str:
    if value is None or bounds is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return "—"
    lo, hi = bounds
    return "✓" if lo <= value <= hi else "✗"


def _is_multi(metrics: dict) -> bool:
    """Heuristic: in multi-seed shape, scalar leaves are dicts with 'per_seed'."""
    v = metrics.get("tree_height")
    return isinstance(v, dict) and "per_seed" in v


def _scalar_value(metrics: dict, key: str) -> float | None:
    v = metrics.get(key)
    if v is None:
        return None
    if isinstance(v, dict) and "mean" in v:
        return v["mean"]
    return v


def _bounds_for(ranges: MetricRanges, field_name: str) -> tuple[float, float] | None:
    return getattr(ranges, field_name, None)


def format_report(
    metrics: dict,
    *,
    ranges: MetricRanges = DEFAULT_RANGES,
    seeds: list[int] | None = None,
    species: str | None = None,
) -> str:
    multi = _is_multi(metrics)
    lines: list[str] = []
    header = "palubicki diagnose"
    if species is not None:
        header += f" — species: {species}"
    if seeds is not None:
        if len(seeds) == 1:
            header += f", seed: {seeds[0]}"
        else:
            header += f", seeds: [{','.join(str(s) for s in seeds)}]"
    lines.append(header)
    lines.append("=" * 72)
    lines.append("")

    def fmt_scalar(v) -> str:
        if v is None:
            return "—"
        if isinstance(v, float) and math.isnan(v):
            return "—"
        if isinstance(v, dict):
            mean = v["mean"]
            stddev = v["stddev"]
            mean_s = "—" if (isinstance(mean, float) and math.isnan(mean)) else f"{mean:.3g}"
            std_s = "—" if (isinstance(stddev, float) and math.isnan(stddev)) else f"{stddev:.3g}"
            return f"{mean_s}  ± {std_s}"
        if isinstance(v, float):
            return f"{v:.3g}"
        return str(v)

    # Architecture section
    lines.append("Architecture")
    for k in ("tree_height", "trunk_base_diameter", "crown_radius", "total_leaf_area"):
        val = metrics.get(k)
        flag = _flag(_scalar_value(metrics, k), _bounds_for(ranges, k))
        lines.append(f"  {k:24s} {fmt_scalar(val):20s} {flag}".rstrip())
    lines.append("")

    # Strahler section
    lines.append("Strahler / Horton")
    lines.append(f"  order_max                {fmt_scalar(metrics.get('strahler_order_max'))}")
    if not multi:
        hist = metrics.get("strahler_order_histogram") or {}
        lines.append(f"  histogram                {dict(sorted(hist.items()))}")
        ratios = metrics.get("horton_bifurcation_ratio") or {}
        if ratios:
            ratio_strs = "   ".join(f"{n}→{n+1}: {r:.3g}" for n, r in sorted(ratios.items()))
            lines.append(f"  bifurcation_ratio        {ratio_strs}")
    flag = _flag(_scalar_value(metrics, "horton_bifurcation_ratio_mean"),
                 _bounds_for(ranges, "horton_bifurcation_ratio_mean"))
    lines.append(f"  bif_ratio_mean           {fmt_scalar(metrics.get('horton_bifurcation_ratio_mean'))}  {flag}".rstrip())
    lines.append("")

    # Angles section
    lines.append("Angles (observed, by child axis_order)")
    for k_pretty, k_dict, range_prefix in [
        ("insertion (vs parent)",      "insertion_angle_deg_vs_parent",      "insertion_angle_deg_vs_parent"),
        ("insertion (vs main sib)",    "insertion_angle_deg_vs_main_sibling", None),
        ("divergence",                  "divergence_angle_deg",                "divergence_angle_deg"),
    ]:
        d = metrics.get(k_dict) or {}
        if not d:
            continue
        lines.append(f"  {k_pretty}")
        for order in sorted(d.keys()):
            stats = d[order]
            flag = ""
            if range_prefix is not None:
                bound_field = f"{range_prefix}__order{order}_mean"
                flag = _flag(_scalar_value({k_dict: {order: stats}}, k_dict) if False else
                             (stats.get("mean") if isinstance(stats, dict) else None),
                             _bounds_for(ranges, bound_field))
            lines.append(f"    order {order}                 {fmt_scalar(stats)}  {flag}".rstrip())
    lines.append("")

    # Counts section
    lines.append("Counts")
    lines.append(f"  sympodial_forks          {fmt_scalar(metrics.get('sympodial_fork_count'))}")
    bh = metrics.get("bud_state_histogram") or {}
    if bh:
        if multi:
            for name in ("ACTIVE", "DORMANT", "DEAD", "RESERVE"):
                if name in bh:
                    lines.append(f"  buds.{name:10s}        {fmt_scalar(bh[name])}")
        else:
            parts = "   ".join(f"{k}: {v}" for k, v in bh.items())
            lines.append(f"  buds                     {parts}")
    return "\n".join(lines)
```

- [ ] **Step 8.4: Run the format_report tests, confirm pass.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -v -k format_report`
Expected: 2 PASS.

- [ ] **Step 8.5: Run the full diagnostics suite.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -v`
Expected: all PASS.

- [ ] **Step 8.6: Commit.**

```bash
git add src/palubicki/sim/diagnostics.py tests/sim/test_diagnostics.py
git commit -m "$(cat <<'EOF'
feat(sim): MetricRanges + format_report pretty-printer

Reference-range flags driven by a small dataclass; auto-detects
single-seed vs multi-seed dict shapes and renders accordingly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: CLI subcommand `palubicki diagnose`

**Goal:** `palubicki diagnose --species oak --seed 0[,1,2,...]` runs `simulate`, computes metrics, prints the report (or JSON).

**Files:**
- Modify: `src/palubicki/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 9.1: Write the four CLI tests (#16–#19).**

Append to `tests/test_cli.py`:

```python
# Append to tests/test_cli.py

@pytest.mark.slow
def test_cli_diagnose_single_seed_runs():
    res = _run("diagnose", "--species", "oak", "--seed", "0")
    assert res.returncode == 0, res.stderr
    assert "tree_height" in res.stdout
    assert "bif_ratio" in res.stdout or "bifurcation_ratio" in res.stdout


@pytest.mark.slow
def test_cli_diagnose_json():
    import json as _json
    res = _run("diagnose", "--species", "oak", "--seed", "0", "--json")
    assert res.returncode == 0, res.stderr
    data = _json.loads(res.stdout)
    assert "tree_height" in data
    assert "strahler_order_max" in data
    assert "horton_bifurcation_ratio_mean" in data


@pytest.mark.slow
def test_cli_diagnose_multi_seed():
    res = _run("diagnose", "--species", "oak", "--seed", "0,1,2")
    assert res.returncode == 0, res.stderr
    assert "mean" in res.stdout
    assert "stddev" in res.stdout


def test_cli_diagnose_bad_seed_list():
    res = _run("diagnose", "--species", "oak", "--seed", "0,foo")
    assert res.returncode == 2
```

- [ ] **Step 9.2: Run, confirm failure (no `diagnose` subcommand yet).**

Run: `.venv/bin/pytest tests/test_cli.py -v -k diagnose`
Expected: FAIL.

- [ ] **Step 9.3: Add the `diagnose` subparser to `_build_parser`.**

Open `src/palubicki/cli.py`. After the `edit` subparser block (around line 117) and before `return parser`, insert:

```python
    dg = sub.add_parser("diagnose", help="Compute and print structural metrics for a generated tree")
    dg.add_argument("--config", type=Path, default=None)
    dg.add_argument("--species",
                    choices=species_choices if species_choices else None,
                    default=None)
    dg.add_argument("--seed", type=_parse_seed_list, default=[0],
                    help="Seed N or comma-separated list N,M,...")
    dg.add_argument("--json", action="store_true",
                    help="Emit raw metrics dict as JSON (skips the report layout)")
    dg.add_argument("--log-level", choices=["DEBUG", "INFO", "WARN", "WARNING", "ERROR"],
                    default="WARNING")
```

Add the `_parse_seed_list` helper near `_parse_size` (around line 123):

```python
def _parse_seed_list(value: str) -> list[int]:
    """Parse 'N' or 'N,M,...' → [int, ...]. Raises ArgumentTypeError on bad input."""
    parts = value.split(",")
    if not parts or any(p.strip() == "" for p in parts):
        raise argparse.ArgumentTypeError(f"invalid --seed {value!r}: empty entry")
    try:
        return [int(p) for p in parts]
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid --seed {value!r}: not all integers")
```

Add the dispatch line in `main(...)`, after the `edit` branch:

```python
    if args.command == "diagnose":
        return _cmd_diagnose(args)
```

Add the handler at the bottom of `cli.py` (before `_config_to_dict`):

```python
def _cmd_diagnose(args) -> int:
    import json

    logging.basicConfig(level=getattr(logging, args.log_level.replace("WARN", "WARNING")),
                        format="%(message)s")

    from palubicki.sim.diagnostics import compute_metrics, format_report

    seeds: list[int] = args.seed if isinstance(args.seed, list) else [args.seed]

    trees = []
    cfg = None  # last cfg loaded; geom params are the same across seeds
    for s in seeds:
        try:
            cfg = load_config(
                yaml_path=args.config,
                cli_overrides={"seed": s},
                output=Path("tree.glb"),
                species=args.species,
            )
        except ConfigError as e:
            print(f"config error: {e}", file=sys.stderr)
            return 2
        try:
            trees.append(simulate(cfg))
        except (ValueError, RuntimeError) as e:
            print(f"diagnose error: {type(e).__name__}: {e}", file=sys.stderr)
            return 1

    metrics = compute_metrics(trees if len(trees) > 1 else trees[0], cfg=cfg)

    if args.json:
        print(json.dumps(metrics, indent=2, default=str))
    else:
        print(format_report(metrics, seeds=seeds, species=args.species))
    return 0
```

- [ ] **Step 9.4: Run the bad-seed-list test first (fast, doesn't run `simulate`).**

Run: `.venv/bin/pytest tests/test_cli.py::test_cli_diagnose_bad_seed_list -v`
Expected: PASS.

- [ ] **Step 9.5: Run a smoke check from the shell.**

Run: `.venv/bin/python -m palubicki.cli diagnose --species oak --seed 0`
Expected: human-readable report on stdout; no traceback.

- [ ] **Step 9.6: Run the remaining slow CLI tests.**

Run: `.venv/bin/pytest tests/test_cli.py -v -k diagnose`
Expected: all 4 PASS.

- [ ] **Step 9.7: Commit.**

```bash
git add src/palubicki/cli.py tests/test_cli.py
git commit -m "$(cat <<'EOF'
feat(cli): palubicki diagnose subcommand

Single- or multi-seed structural-metrics report for a generated
tree. Mirrors generate for config loading; --json emits the raw
metrics dict for piping. Covers spec tests #16–#19.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Integration tests + final regression check

**Goal:** Test #13 (bifurcation ratio sane per species) and #14 (diagnostics doesn't mutate the tree). Finally verify nothing else broke.

**Files:**
- Modify: `tests/sim/test_diagnostics.py`

- [ ] **Step 10.1: Add test #14 (read-only invariant).**

```python
# Append to tests/sim/test_diagnostics.py

@pytest.mark.slow
def test_diagnostics_doesnt_mutate_tree():
    """Snapshot a few invariants on the tree, run compute_metrics, verify
    they still match. This is the load-bearing guard that the harness is
    truly read-only."""
    from palubicki.config import load_config
    from palubicki.sim.simulator import simulate

    cfg = load_config(yaml_path=None, cli_overrides={"seed": 0},
                      output=Path("tree.glb"), species="oak")
    tree = simulate(cfg)

    before_internodes = len(tree.all_internodes)
    before_active = len(tree.active_buds)
    before_root_id = id(tree.root)
    before_sympodial = sum(
        1 for iod in tree.all_internodes for n in (iod.parent_node, iod.child_node)
        if n.sympodial_fork
    )

    _ = compute_metrics(tree, cfg=cfg)

    assert len(tree.all_internodes) == before_internodes
    assert len(tree.active_buds) == before_active
    assert id(tree.root) == before_root_id
    after_sympodial = sum(
        1 for iod in tree.all_internodes for n in (iod.parent_node, iod.child_node)
        if n.sympodial_fork
    )
    assert after_sympodial == before_sympodial
```

- [ ] **Step 10.2: Add test #13 (bifurcation ratio sane per species).**

```python
# Append to tests/sim/test_diagnostics.py

@pytest.mark.slow
@pytest.mark.parametrize("species", ["oak", "birch", "pine", "maple"])
def test_bifurcation_ratio_in_sane_range_per_species(species):
    """Acceptance criterion: each preset's bif_ratio_mean falls in
    [2.5, 6.0] for seed 0."""
    from palubicki.config import load_config
    from palubicki.sim.simulator import simulate

    cfg = load_config(yaml_path=None, cli_overrides={"seed": 0},
                      output=Path("tree.glb"), species=species)
    tree = simulate(cfg)
    m = compute_metrics(tree, cfg=cfg)
    bif = m["horton_bifurcation_ratio_mean"]
    assert not math.isnan(bif), f"{species}: bif_ratio_mean is NaN — tree may be degenerate"
    assert 2.5 <= bif <= 6.0, f"{species}: bif_ratio_mean={bif:.3f} outside [2.5, 6.0]"
```

- [ ] **Step 10.3: Run the two new integration tests.**

Run: `.venv/bin/pytest tests/sim/test_diagnostics.py -v -k "doesnt_mutate or sane_range"`
Expected: 5 PASS (1 mutation + 4 species).

If a species fails the [2.5, 6.0] sanity range:
- Investigate whether it's the species' actual structure (acceptable — loosen the bound and document) or a bug in the harness (Strahler / counting). Do not silently widen the bound to hide a harness bug.
- If a real-tree result is just outside the bound (e.g., bif=2.45 for pine), discuss before relaxing — the acceptance criterion is loose intentionally; out-of-range should be rare.

- [ ] **Step 10.4: Run the full repo test suite for regressions.**

Run: `.venv/bin/pytest`
Expected: same set of passes / pre-existing skipped / pre-existing failures as before the branch. **No new failures.**

If any pre-existing golden tests fail: do NOT modify the golden. Investigate whether the Task 5 leaf extraction silently shifted anything. If you cannot reconcile, surface the failure rather than papering over it.

- [ ] **Step 10.5: Commit.**

```bash
git add tests/sim/test_diagnostics.py
git commit -m "$(cat <<'EOF'
test(sim): integration tests for diagnostics harness

#13: bif_ratio_mean in [2.5, 6.0] for oak/birch/pine/maple seed 0.
#14: compute_metrics doesn't mutate Tree state (read-only invariant).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 10.6: Push the branch.**

```bash
git push
```

The PR (#13) is already open as draft; the user will mark ready-for-review themselves.

---

## Spec-coverage check (after all tasks done)

Map every acceptance-criterion line to the task that covers it:

| Spec criterion | Task |
|---|---|
| `compute_metrics(tree)` returns all minimum-viable keys | Tasks 1–6 |
| `palubicki diagnose --species oak --seed 0` prints all metrics | Task 9 |
| Strahler unit-tested against a known small tree | Task 1 (tests #1–#3) |
| Bifurcation ratio in [2.5, 6.0] per species | Task 10 (test #13) |
| No change to `simulate(...)` or any existing golden | Task 10 (test #14) + leaf-parity test in Task 5 + no goldens deleted |
| ✓/✗ literature-range flags | Task 8 |
| Multi-seed comparison | Task 7 + Task 9 (CLI `--seed N,M,...`) |
| `--json` output | Task 9 |
| Refactor C — `compute_effective_leaf_size` | Task 5 |
