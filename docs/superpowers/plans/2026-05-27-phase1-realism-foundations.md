# Phase 1 — Fondations de réalisme — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `palubicki` trees more biologically realistic by giving tropisms a main-vs-lateral split, adding gaussian jitter to phyllotaxy angles, and making `internode_length` stochastic.

**Architecture:** Three small additive changes in `config.py`, `tropisms.py`, `phyllotaxy.py`, `simulator.py`. Deterministic RNG per call site derived from `cfg.seed` via `np.random.SeedSequence([seed, kind, ...]).generate_state(1)`. The 3 preset YAMLs are rewritten using only the new field names. The legacy `_apply_section_aliases` helper is deleted.

**Tech Stack:** Python 3.x, NumPy (RNG), pytest. PoC mode — pas de backward-compat sur les YAML, les API ou les goldens.

**Reference spec:** `docs/superpowers/specs/2026-05-27-phase1-realism-foundations-design.md`

---

## Pre-flight

Avant de commencer toute tâche, vérifier que la suite passe au point de départ.

- [ ] **Run baseline**

```bash
cd /Users/julienriel/src/palubicki
.venv/bin/pytest -x --no-header -q 2>&1 | tail -10
```

Expected: `passed` (la suite passe avant qu'on touche à quoi que ce soit).

---

## Task 1 : Refactor `TropismConfig` (main/lateral split, suppression des champs legacy)

**Files:**
- Modify: `src/palubicki/config.py` (TropismConfig dataclass, Config.__post_init__, remove `_apply_section_aliases`)
- Modify: `tests/test_config.py` (lignes 23-37)
- Modify: `tests/test_config_yaml.py` (aucune ligne ne casse, à vérifier)

- [ ] **Step 1 : Lire l'état actuel des fichiers concernés**

```bash
.venv/bin/python -c "from palubicki.config import TropismConfig; t=TropismConfig(); print(t)"
```

Expected: print avec `w_orthotropy=0.3, w_gravitropism=0.0, ...`

- [ ] **Step 2 : Écrire le test attendu pour le nouveau `TropismConfig`**

Édite `tests/test_config.py` — remplace `test_config_with_defaults_is_valid` (lignes 23-27) :

```python
def test_config_with_defaults_is_valid(tmp_path):
    cfg = _make_config(output=tmp_path / "out.glb")
    assert cfg.sim.max_iterations == 30
    assert cfg.tropism.w_orthotropy_main == 0.3
    assert cfg.tropism.w_orthotropy_lateral == 0.1
    assert cfg.tropism.w_gravitropism_main == 0.0
    assert cfg.tropism.w_gravitropism_lateral == 0.0
```

Supprime entièrement `test_legacy_w_gravity_yaml_alias_maps_to_w_orthotropy` (lignes 29-37).

Ajoute deux nouveaux tests à la fin du fichier (avant le bloc `_make_config` ou en fin) :

```python
def test_config_rejects_negative_w_orthotropy_main(tmp_path):
    with pytest.raises(ConfigError, match="w_orthotropy_main"):
        _make_config(
            tropism=TropismConfig(w_orthotropy_main=-0.1),
            output=tmp_path / "out.glb",
        )


def test_config_rejects_negative_w_gravitropism_lateral(tmp_path):
    with pytest.raises(ConfigError, match="w_gravitropism_lateral"):
        _make_config(
            tropism=TropismConfig(w_gravitropism_lateral=-0.2),
            output=tmp_path / "out.glb",
        )
```

- [ ] **Step 3 : Exécuter ces tests, vérifier qu'ils échouent**

```bash
.venv/bin/pytest tests/test_config.py::test_config_with_defaults_is_valid tests/test_config.py::test_config_rejects_negative_w_orthotropy_main tests/test_config.py::test_config_rejects_negative_w_gravitropism_lateral -v
```

Expected: 3 tests FAIL (le premier sur `w_orthotropy_main` n'existe pas ; les deux validations n'existent pas non plus).

- [ ] **Step 4 : Mettre à jour `TropismConfig` dans `config.py`**

Dans `src/palubicki/config.py`, remplace le bloc `TropismConfig` (lignes 51-67) par :

```python
@dataclass(frozen=True)
class TropismConfig:
    w_perception: float = field(default=1.0, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    # Orthotropy = pull toward +Y. Distinct main-vs-lateral weights so axe principal
    # can stay vertical while latéraux open horizontally (oak/birch) or stay
    # near-horizontal (pine whorls).
    w_orthotropy_main: float = field(default=0.3, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    w_orthotropy_lateral: float = field(default=0.1, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    # Gravitropism = pull toward -Y. Distinct main vs lateral so e.g. birch
    # pendula can droop its laterals while the trunk stays vertical.
    w_gravitropism_main: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    w_gravitropism_lateral: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    w_phototropism: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    w_direction_inertia: float = field(default=0.4, metadata={"ui": {"min": 0.0, "max": 3.0, "step": 0.05}})
    photo_direction: tuple[float, float, float] = (0.0, 1.0, 0.0)  # not exposed; vec3 stays defaulted
    axis_decay: float = field(default=1.0, metadata={"ui": {"min": 0.1, "max": 1.0, "step": 0.05}})
```

- [ ] **Step 5 : Ajouter la validation dans `Config.__post_init__`**

Dans `config.py`, après le bloc `s = self.sim ; if not (0 < s.theta_perception_deg <= 180): ...` (autour de la ligne 222), insère **avant la section geom** :

```python
        t = self.tropism
        for fname in (
            "w_orthotropy_main", "w_orthotropy_lateral",
            "w_gravitropism_main", "w_gravitropism_lateral",
        ):
            v = getattr(t, fname)
            if v < 0:
                raise ConfigError(f"tropism.{fname} must be >= 0, got {v}")
```

- [ ] **Step 6 : Supprimer `_apply_section_aliases`**

Dans `config.py`, supprime entièrement la fonction `_apply_section_aliases` (lignes 277-283) et son call site dans `load_config` (ligne 310) :

Remplace :
```python
    for name, type_ in _SECTION_TYPES.items():
        sec_data = _apply_section_aliases(name, data.get(name, {}) or {})
        allowed = {f.name for f in fields(type_)}
```

Par :
```python
    for name, type_ in _SECTION_TYPES.items():
        sec_data = data.get(name, {}) or {}
        allowed = {f.name for f in fields(type_)}
```

- [ ] **Step 7 : Exécuter les tests config**

```bash
.venv/bin/pytest tests/test_config.py -v 2>&1 | tail -30
```

Expected: tous les tests de `test_config.py` PASS. À ce stade, `test_config_yaml.py`, `test_config_species.py`, tous les tests sim et goldens cassent — c'est normal, on les corrige dans les tâches suivantes.

- [ ] **Step 8 : Commit**

```bash
git add src/palubicki/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
refactor(config): split tropism weights into main/lateral pair

Replaces w_orthotropy and w_gravitropism with explicit
w_orthotropy_main/_lateral and w_gravitropism_main/_lateral pairs.
Removes _apply_section_aliases (legacy w_gravity → w_orthotropy mapping).
Adds validation that the 4 new weights are non-negative.

Phase 1 of realism-foundations spec.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 : Plumb `is_main_axis` through `growth_direction` + `simulator`

**Files:**
- Modify: `src/palubicki/sim/tropisms.py` (signature + body)
- Modify: `src/palubicki/sim/simulator.py` (call site, ~ligne 166-172)
- Modify: `tests/sim/test_tropisms.py` (chaque appel à `growth_direction` + nouveaux tests)

- [ ] **Step 1 : Écrire le test du nouveau comportement**

Édite `tests/sim/test_tropisms.py`, ajoute en fin de fichier :

```python
def test_main_axis_uses_main_orthotropy_weight():
    """With w_orthotropy_main=1.0 and w_orthotropy_lateral=0.0, a main axis
    should be pulled UP; a lateral axis should ignore orthotropy entirely."""
    cfg = TropismConfig(
        w_perception=0.0,
        w_orthotropy_main=1.0,
        w_orthotropy_lateral=0.0,
        w_phototropism=0.0,
        w_direction_inertia=0.0,
    )
    # main axis: orthotropy pulls UP
    d_main = growth_direction(
        v_perception=np.array([1.0, 0.0, 0.0]),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
        is_main_axis=True,
    )
    np.testing.assert_allclose(d_main, [0, 1, 0], atol=1e-7)

    # lateral axis: no orthotropy → falls back to current_direction (only non-zero weight)
    # but all weights are zero on lateral side, so use inertia=0 path → returns inertia fallback
    # We add a tiny inertia so the test is unambiguous:
    cfg2 = TropismConfig(
        w_perception=0.0,
        w_orthotropy_main=1.0,
        w_orthotropy_lateral=0.0,
        w_phototropism=0.0,
        w_direction_inertia=1.0,
    )
    d_lat = growth_direction(
        v_perception=np.array([1.0, 0.0, 0.0]),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg2,
        is_main_axis=False,
    )
    np.testing.assert_allclose(d_lat, [1, 0, 0], atol=1e-7)


def test_lateral_axis_uses_lateral_gravitropism_weight():
    """With w_gravitropism_lateral=1.0 (pendula-like), a lateral axis is pulled DOWN."""
    cfg = TropismConfig(
        w_perception=0.0,
        w_orthotropy_main=0.0,
        w_orthotropy_lateral=0.0,
        w_gravitropism_main=0.0,
        w_gravitropism_lateral=1.0,
        w_direction_inertia=0.0,
    )
    d_lat = growth_direction(
        v_perception=np.array([1.0, 0.0, 0.0]),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
        is_main_axis=False,
    )
    np.testing.assert_allclose(d_lat, [0, -1, 0], atol=1e-7)
```

- [ ] **Step 2 : Mettre à jour les 9 tests existants de `test_tropisms.py` pour passer `is_main_axis`**

Pour **chaque** appel à `growth_direction` déjà présent dans le fichier, ajouter `is_main_axis=True` en kwarg. Et remplacer les anciens kwargs `w_orthotropy=` par `w_orthotropy_main=` :

Édite **chaque** test du fichier comme suit (exemple pour `test_only_gravity_overrides_to_up`) :

```python
def test_only_gravity_overrides_to_up():
    cfg = TropismConfig(w_perception=0.0, w_orthotropy_main=1.0, w_phototropism=0.0, w_direction_inertia=0.0)
    d = growth_direction(
        v_perception=np.array([1.0, 0.0, 0.0]),
        current_direction=np.array([1.0, 0.0, 0.0]),
        cfg=cfg,
        is_main_axis=True,
    )
    np.testing.assert_allclose(d, [0, 1, 0], atol=1e-7)
```

Applique le même pattern à : `test_only_inertia_keeps_current_direction`, `test_all_zero_weights_returns_inertia_fallback`, `test_phototropism_pulls_toward_photo_direction`, `test_returns_unit_vector`, `test_zero_weights_zero_current_direction_falls_back_to_gravity`, `test_growth_direction_uses_light_gradient_when_provided`, `test_growth_direction_falls_back_to_photo_direction_when_no_gradient`, `test_growth_direction_zero_gradient_falls_back_to_photo_direction`, `test_growth_direction_v1_signature_still_works`.

Note : `test_growth_direction_v1_signature_still_works` peut être renommé `test_growth_direction_minimal_kwargs` (le commentaire `# V1 signature` n'a plus de sens — on n'a plus de compat à maintenir).

- [ ] **Step 3 : Exécuter les tests, vérifier qu'ils échouent**

```bash
.venv/bin/pytest tests/sim/test_tropisms.py -v 2>&1 | tail -20
```

Expected: tous les tests FAIL avec `growth_direction() got an unexpected keyword argument 'is_main_axis'` ou `TropismConfig() got an unexpected keyword argument 'w_orthotropy_main'`.

- [ ] **Step 4 : Mettre à jour `growth_direction`**

Remplace le contenu complet de `src/palubicki/sim/tropisms.py` par :

```python
# src/palubicki/sim/tropisms.py
from __future__ import annotations

import numpy as np

from palubicki.config import TropismConfig

_UP = np.array([0.0, 1.0, 0.0])
_DOWN = np.array([0.0, -1.0, 0.0])


def growth_direction(
    *,
    v_perception: np.ndarray,
    current_direction: np.ndarray,
    cfg: TropismConfig,
    is_main_axis: bool,
    light_gradient: np.ndarray | None = None,
    axis_order: int = 0,
) -> np.ndarray:
    """Blend perception + orthotropy (UP) + gravitropy (DOWN) + photo + inertia.

    ``is_main_axis`` selects between the main-axis weights (e.g. w_orthotropy_main)
    and the lateral-axis weights. Each tropism weight at order k is multiplied by
    ``cfg.axis_decay**k``.
    """
    if light_gradient is not None:
        lg = np.asarray(light_gradient, dtype=np.float64)
        lg_norm = float(np.linalg.norm(lg))
        if lg_norm > 1e-12:
            photo = lg / lg_norm
        else:
            photo = np.asarray(cfg.photo_direction, dtype=np.float64)
            pn = np.linalg.norm(photo)
            if pn > 1e-12:
                photo = photo / pn
    else:
        photo = np.asarray(cfg.photo_direction, dtype=np.float64)
        pn = np.linalg.norm(photo)
        if pn > 1e-12:
            photo = photo / pn

    decay = float(cfg.axis_decay) ** int(axis_order)
    w_ortho = cfg.w_orthotropy_main if is_main_axis else cfg.w_orthotropy_lateral
    w_gravi = cfg.w_gravitropism_main if is_main_axis else cfg.w_gravitropism_lateral
    blend = (
        cfg.w_perception * v_perception
        + (w_ortho * decay) * _UP
        + (w_gravi * decay) * _DOWN
        + (cfg.w_phototropism * decay) * photo
        + cfg.w_direction_inertia * current_direction
    )
    n = np.linalg.norm(blend)
    if n < 1e-12:
        cd_n = np.linalg.norm(current_direction)
        if cd_n > 1e-12:
            return current_direction / cd_n
        return _UP.copy()
    return blend / n
```

- [ ] **Step 5 : Mettre à jour le call site dans `simulator.py`**

Dans `src/palubicki/sim/simulator.py`, lignes 166-172 actuellement :

```python
                d = growth_direction(
                    v_perception=res.direction[cur],
                    current_direction=cur.direction,
                    cfg=cfg.tropism,
                    light_gradient=light_grad,
                    axis_order=cur.axis_order,
                )
```

Remplace par :

```python
                is_main = (cur is cur.parent_node.terminal_bud)
                d = growth_direction(
                    v_perception=res.direction[cur],
                    current_direction=cur.direction,
                    cfg=cfg.tropism,
                    is_main_axis=is_main,
                    light_gradient=light_grad,
                    axis_order=cur.axis_order,
                )
```

Note : la ligne `is_main_axis=(cur is cur.parent_node.terminal_bud)` apparaît déjà 30 lignes plus bas pour construire l'Internode (ligne ~202). On peut réutiliser `is_main` à cet endroit aussi pour ne pas recalculer :

Remplace (ligne ~202) :
```python
                iod = Internode(
                    parent_node=cur.parent_node,
                    child_node=new_node,
                    length=cfg.sim.internode_length,
                    is_main_axis=(cur is cur.parent_node.terminal_bud),
                    window=cfg.shedding.window,
                )
```

Par :
```python
                iod = Internode(
                    parent_node=cur.parent_node,
                    child_node=new_node,
                    length=cfg.sim.internode_length,
                    is_main_axis=is_main,
                    window=cfg.shedding.window,
                )
```

- [ ] **Step 6 : Exécuter `test_tropisms.py` + tests simulator**

```bash
.venv/bin/pytest tests/sim/test_tropisms.py tests/sim/test_simulator.py -v 2>&1 | tail -30
```

Expected: tous les tests de `test_tropisms.py` PASS. `test_simulator.py` peut encore casser à cause des goldens internes ou de `test_config_species.py` mais les tests de bas niveau passent.

- [ ] **Step 7 : Commit**

```bash
git add src/palubicki/sim/tropisms.py src/palubicki/sim/simulator.py tests/sim/test_tropisms.py
git commit -m "$(cat <<'EOF'
feat(tropisms): is_main_axis selects between main/lateral weights

growth_direction now requires is_main_axis: bool and routes to
w_orthotropy_main vs _lateral (and same for gravitropism). The simulator
computes is_main from (cur is parent_node.terminal_bud) — same predicate
already used to mark the Internode's is_main_axis flag.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 : Réécrire les YAML presets (oak / pine / birch)

**Files:**
- Modify: `src/palubicki/configs/species/oak.yaml`
- Modify: `src/palubicki/configs/species/pine.yaml`
- Modify: `src/palubicki/configs/species/birch.yaml`
- Modify: `tests/test_config_species.py` (lignes 81-83, 87-93, 96-103, 106-115)
- Modify: `tests/test_config_yaml.py` (ligne 90, 98, 110 — overrides)

- [ ] **Step 1 : Écrire les nouvelles assertions de presets**

Édite `tests/test_config_species.py`, remplace `test_load_preset_birch` (lignes 75-84) :

```python
def test_load_preset_birch(tmp_path):
    cfg = load_config(yaml_path=None, cli_overrides={},
                      output=tmp_path / "x.glb", species="birch")
    assert cfg.envelope.shape == "ellipsoid"
    # Birch preset: strong orthotropic trunk, lateral axes have a real downward
    # gravitropic pull (the pendula effect). Sag stays enabled but attenuated.
    assert cfg.tropism.w_orthotropy_main == pytest.approx(0.40)
    assert cfg.tropism.w_orthotropy_lateral == pytest.approx(0.10)
    assert cfg.tropism.w_gravitropism_lateral == pytest.approx(0.15)
    assert cfg.phyllotaxy.divergence_jitter_deg == pytest.approx(5.0)
    assert cfg.sag.enabled is True
    assert cfg.sag.k == pytest.approx(0.010)
```

Édite `test_user_yaml_overrides_preset` (lignes 87-94) :

```python
def test_user_yaml_overrides_preset(tmp_path):
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text("tropism:\n  w_orthotropy_main: 0.99\n")
    cfg = load_config(yaml_path=user_yaml, cli_overrides={},
                      output=tmp_path / "x.glb", species="oak")
    assert cfg.tropism.w_orthotropy_main == pytest.approx(0.99)
    assert cfg.envelope.shape == "half_ellipsoid"
    assert cfg.geom.leaf_cluster_count == 3
```

Édite `test_cli_override_wins_over_user_yaml` (lignes 97-103) :

```python
def test_cli_override_wins_over_user_yaml(tmp_path):
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text("tropism:\n  w_orthotropy_main: 0.5\n")
    cfg = load_config(yaml_path=user_yaml,
                      cli_overrides={"tropism.w_orthotropy_main": 0.1},
                      output=tmp_path / "x.glb", species="oak")
    assert cfg.tropism.w_orthotropy_main == pytest.approx(0.1)
```

Édite `test_deep_merge_preserves_sibling_sections` (lignes 106-115) :

```python
def test_deep_merge_preserves_sibling_sections(tmp_path):
    """User YAML touching only `tropism` must not erase preset's `envelope` or `phyllotaxy`."""
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text("tropism:\n  w_orthotropy_main: 0.3\n")
    cfg = load_config(yaml_path=user_yaml, cli_overrides={},
                      output=tmp_path / "x.glb", species="pine")
    assert cfg.envelope.shape == "cone"
    assert cfg.phyllotaxy.mode == "whorled"
    assert cfg.geom.leaf_cluster_count == 5
    assert cfg.tropism.w_orthotropy_main == pytest.approx(0.3)
```

Édite aussi `tests/test_config_yaml.py` : ligne 90-99 (le test `test_load_config_with_forest_seeds`) référence `tropism.w_orthotropy` dans la map d'overrides — remplace par `tropism.w_orthotropy_main` :

```python
        - position: [5.0, 0.0, 0.0]
          seed: 42
          overrides:
            envelope.shape: cone
            tropism.w_orthotropy_main: 0.5
""")
    cfg = load_config(yaml_path=yaml_path, cli_overrides={}, output=tmp_path / "out.glb")
    ...
    assert cfg.forest.seeds[1].overrides == {"envelope.shape": "cone", "tropism.w_orthotropy_main": 0.5}
```

- [ ] **Step 2 : Exécuter ces tests, vérifier qu'ils échouent**

```bash
.venv/bin/pytest tests/test_config_species.py tests/test_config_yaml.py -v 2>&1 | tail -20
```

Expected: 4-5 FAILs (le preset birch a encore les anciens champs, et l'override `w_orthotropy_main` ne match pas).

- [ ] **Step 3 : Réécrire `src/palubicki/configs/species/oak.yaml`**

Remplace tout le contenu du fichier par :

```yaml
# Quercus robur — dense, étalé, ramure tortueuse
envelope:
  shape: half_ellipsoid
  rx: 5.0
  ry: 6.5
  rz: 5.0
  marker_count: 25000
sim:
  internode_length: 0.18
  internode_length_jitter: 0.12
  # Oak: moderate apical dominance.
  lambda_apical: 0.75
  alpha_basipetal: 2.2
  max_iterations: 45
tropism:
  # Oak: strong orthotropic trunk, primary branches go more horizontal.
  w_orthotropy_main: 0.35
  w_orthotropy_lateral: 0.05
  w_gravitropism_main: 0.0
  w_gravitropism_lateral: 0.0
  w_phototropism: 0.35
  w_direction_inertia: 0.5
  axis_decay: 0.65
phyllotaxy:
  mode: alternate
  divergence_angle_deg: 137.5
  divergence_jitter_deg: 6.0
  branch_angle_deg: 60
  branch_angle_jitter_deg: 5.0
shedding:
  quality_threshold: 0.15
light:
  enabled: true
  k_absorption: 0.55
sag:
  enabled: true
  k: 0.005
  max_bend_deg: 5.0
  rigid_axis_order: 1
geom:
  ring_sides: 10
  pipe_exponent: 2.3
  r_tip: 0.008
  bark_color: [0.32, 0.22, 0.14]
  bark_texture: "proc:oak_bark"
  leaf_texture: "proc:oak_leaf"
  leaf_size: 0.14
  leaf_cluster_count: 3
  leaf_aspect: 1.0
  leaf_splay_deg: 25
  foliage_depth: 4
```

- [ ] **Step 4 : Réécrire `src/palubicki/configs/species/pine.yaml`**

Remplace tout le contenu par :

```yaml
# Pinus sylvestris — conifère conique, étages réguliers, apical dominant
envelope:
  shape: cone
  rx: 2.5
  ry: 9.0
  rz: 2.5
  marker_count: 18000
sim:
  internode_length: 0.18
  internode_length_jitter: 0.08
  lambda_apical: 0.85
  alpha_basipetal: 1.8
  max_iterations: 40
tropism:
  # Conifer: strict apical dominance, near-horizontal whorl laterals.
  w_orthotropy_main: 0.30
  w_orthotropy_lateral: 0.05
  w_gravitropism_main: 0.0
  w_gravitropism_lateral: 0.02
  w_phototropism: 0.20
  w_direction_inertia: 0.8
  axis_decay: 0.85
phyllotaxy:
  mode: whorled
  whorl_count: 5
  divergence_angle_deg: 72
  divergence_jitter_deg: 3.0
  branch_angle_deg: 75
  branch_angle_jitter_deg: 4.0
shedding:
  quality_threshold: 0.20
light:
  enabled: true
  k_absorption: 0.65
geom:
  ring_sides: 8
  pipe_exponent: 2.3
  r_tip: 0.007
  bark_color: [0.45, 0.25, 0.18]
  bark_texture: "proc:pine_bark"
  leaf_texture: "proc:pine_needle"
  leaf_size: 0.06
  leaf_cluster_count: 5
  leaf_aspect: 0.025
  leaf_splay_deg: 25
  foliage_depth: 3
```

- [ ] **Step 5 : Réécrire `src/palubicki/configs/species/birch.yaml`**

Remplace tout le contenu par :

```yaml
# Betula pendula — élancé, branches fines, port pleureur
envelope:
  shape: ellipsoid
  rx: 2.5
  ry: 7.0
  rz: 2.5
  marker_count: 20000
sim:
  internode_length: 0.18
  internode_length_jitter: 0.15
  # Birch has very strong apical dominance — single straight leader.
  lambda_apical: 0.95
  alpha_basipetal: 2.0
  max_iterations: 45
tropism:
  # Pendula: trunk strictly orthotropic, lateral axes get a real downward pull.
  # This is the proper plagiotropism mechanism; the sag pass below is now a
  # complementary touch, not the primary droop source.
  w_orthotropy_main: 0.40
  w_orthotropy_lateral: 0.10
  w_gravitropism_main: 0.0
  w_gravitropism_lateral: 0.15
  w_phototropism: 0.25
  w_direction_inertia: 0.50
  axis_decay: 0.85
sag:
  enabled: true
  k: 0.010
  max_bend_deg: 6.0
  rigid_axis_order: 2
phyllotaxy:
  mode: alternate
  divergence_angle_deg: 137.5
  divergence_jitter_deg: 5.0
  branch_angle_deg: 45
  branch_angle_jitter_deg: 4.0
shedding:
  # Pendula self-shadows heavily; threshold must be very permissive.
  quality_threshold: 0.02
light:
  enabled: true
  k_absorption: 0.45
geom:
  ring_sides: 8
  pipe_exponent: 2.25
  r_tip: 0.006
  bark_color: [0.85, 0.82, 0.75]
  bark_texture: "proc:birch_bark"
  leaf_texture: "proc:birch_leaf"
  leaf_size: 0.05
  leaf_cluster_count: 3
  leaf_aspect: 0.7
  leaf_splay_deg: 20
  foliage_depth: 3
```

Note : les YAML référencent `divergence_jitter_deg`, `branch_angle_jitter_deg`, `internode_length_jitter` qui **n'existent pas encore** dans `PhyllotaxyConfig`/`SimConfig`. On va les ajouter en Tâches 4 et 5. À ce stade, le chargement YAML va échouer avec `ConfigError: unknown keys in section`. C'est normal — on règle ça avec la Tâche 4 immédiatement après.

- [ ] **Step 6 : Vérifier que les tests config presets cassent comme attendu (champs jitter inconnus)**

```bash
.venv/bin/pytest tests/test_config_species.py -v 2>&1 | tail -10
```

Expected: tous FAIL avec `unknown keys in section 'phyllotaxy': ['branch_angle_jitter_deg', 'divergence_jitter_deg']` ou similaire pour `sim`. On ne commit pas tant que ce n'est pas vert — on enchaîne la Tâche 4 puis on commit ensemble.

**Note** : il n'y a **pas** de commit à la fin de cette tâche. Cette tâche prépare les YAML qui dépendent des champs introduits en Tâche 4 et 5. Le commit a lieu après la Tâche 5 (commit groupé "presets + new jitter fields").

---

## Task 4 : Ajouter le jitter phyllotaxique

**Files:**
- Modify: `src/palubicki/config.py` (PhyllotaxyConfig + validation)
- Modify: `src/palubicki/sim/phyllotaxy.py` (signature + jitter logic)
- Modify: `src/palubicki/sim/simulator.py` (call site avec `seed=cfg.seed`)
- Modify: `tests/sim/test_phyllotaxy.py` (chaque appel reçoit `seed=` + nouveaux tests)

- [ ] **Step 1 : Écrire les nouveaux tests de jitter**

Édite `tests/sim/test_phyllotaxy.py`, ajoute en fin de fichier :

```python
def test_jitter_deterministic_same_seed():
    """Same seed + same node_index → identical jittered direction."""
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_deg=45.0,
        divergence_angle_deg=137.5,
        divergence_jitter_deg=5.0,
        branch_angle_jitter_deg=5.0,
    )
    d_a = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=42)
    d_b = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=42)
    np.testing.assert_array_equal(d_a, d_b)


def test_jitter_different_seeds_differ():
    """Same node_index, different seeds → different jittered directions."""
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_deg=45.0,
        divergence_angle_deg=137.5,
        divergence_jitter_deg=5.0,
        branch_angle_jitter_deg=5.0,
    )
    d_a = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=42)
    d_b = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=43)
    assert not np.allclose(d_a, d_b, atol=1e-6)


def test_jitter_zero_matches_no_jitter():
    """With both sigmas == 0, the result is identical regardless of seed."""
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_deg=45.0,
        divergence_angle_deg=137.5,
        divergence_jitter_deg=0.0,
        branch_angle_jitter_deg=0.0,
    )
    d_a = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=42)
    d_b = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=3, seed=99)
    np.testing.assert_array_equal(d_a, d_b)


def test_jitter_clamps_branch_angle_in_range():
    """With a huge branch_angle_jitter_deg, the effective angle stays in [0, 90°]."""
    cfg = PhyllotaxyConfig(
        mode="alternate",
        branch_angle_deg=45.0,
        divergence_angle_deg=137.5,
        divergence_jitter_deg=0.0,
        branch_angle_jitter_deg=500.0,  # absurd σ
    )
    growth = np.array([0, 1, 0])
    for ni in range(50):
        d = lateral_bud_directions(growth, cfg, node_index=ni, seed=42)[0]
        cos_with_growth = float(np.dot(d, growth))
        # branch_angle in [0, 90°] ⇒ cos in [0, 1]
        assert -1e-9 <= cos_with_growth <= 1.0 + 1e-9, (
            f"node_index={ni}: cos(growth, d)={cos_with_growth} outside [0, 1]"
        )
```

Mettre à jour les 5 tests existants pour passer `seed=0` :

Pour chaque test existant (`test_alternate_yields_one_direction`, `test_opposite_yields_two_opposing_directions`, `test_whorled_yields_k_directions`, `test_branch_angle_respected`, `test_alternate_divergence_rotates_between_nodes`), ajoute `seed=0` dans l'appel à `lateral_bud_directions`. Exemple :

```python
def test_alternate_yields_one_direction():
    cfg = PhyllotaxyConfig(mode="alternate", branch_angle_deg=45.0, divergence_angle_deg=137.5)
    dirs = lateral_bud_directions(np.array([0, 1, 0]), cfg, node_index=0, seed=0)
    assert dirs.shape == (1, 3)
    assert abs(np.linalg.norm(dirs[0]) - 1.0) < 1e-7
```

- [ ] **Step 2 : Exécuter, vérifier qu'ils échouent**

```bash
.venv/bin/pytest tests/sim/test_phyllotaxy.py -v 2>&1 | tail -20
```

Expected: tous FAIL avec `lateral_bud_directions() got an unexpected keyword argument 'seed'` ou `PhyllotaxyConfig() got unexpected keyword 'divergence_jitter_deg'`.

- [ ] **Step 3 : Mettre à jour `PhyllotaxyConfig`**

Dans `src/palubicki/config.py`, remplace le bloc `PhyllotaxyConfig` (lignes 70-77) par :

```python
@dataclass(frozen=True)
class PhyllotaxyConfig:
    mode: Literal["alternate", "opposite", "whorled"] = field(
        default="alternate", metadata={"ui": {"label": "Mode"}}
    )
    whorl_count: int = field(default=3, metadata={"ui": {"min": 2, "max": 8, "step": 1}})
    divergence_angle_deg: float = field(default=137.5, metadata={"ui": {"min": 0.0, "max": 360.0, "step": 0.5}})
    branch_angle_deg: float = field(default=45.0, metadata={"ui": {"min": 0.0, "max": 90.0, "step": 1.0}})
    # Gaussian jitter (σ in degrees) on the azimuthal divergence between
    # successive lateral buds. 4-6° matches realistic biological variability.
    divergence_jitter_deg: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 30.0, "step": 0.5}})
    # Gaussian jitter on the branch insertion angle. Clamped to [0°, 90°].
    branch_angle_jitter_deg: float = field(default=0.0, metadata={"ui": {"min": 0.0, "max": 20.0, "step": 0.5}})
```

- [ ] **Step 4 : Ajouter validation dans `Config.__post_init__`**

Dans `config.py`, juste après les validations tropism (ajoutées Tâche 1), insère :

```python
        p = self.phyllotaxy
        if p.divergence_jitter_deg < 0:
            raise ConfigError(
                f"phyllotaxy.divergence_jitter_deg must be >= 0, got {p.divergence_jitter_deg}"
            )
        if p.branch_angle_jitter_deg < 0:
            raise ConfigError(
                f"phyllotaxy.branch_angle_jitter_deg must be >= 0, got {p.branch_angle_jitter_deg}"
            )
```

- [ ] **Step 5 : Mettre à jour `phyllotaxy.py`**

Remplace le contenu complet de `src/palubicki/sim/phyllotaxy.py` par :

```python
# src/palubicki/sim/phyllotaxy.py
from __future__ import annotations

import math

import numpy as np

from palubicki.config import PhyllotaxyConfig


def lateral_bud_directions(
    growth_direction: np.ndarray,
    cfg: PhyllotaxyConfig,
    node_index: int,
    *,
    seed: int,
) -> np.ndarray:
    """Return (K, 3) unit vectors for lateral bud directions at this node.

    If ``cfg.divergence_jitter_deg`` or ``cfg.branch_angle_jitter_deg`` is > 0,
    a gaussian perturbation is drawn from a per-(seed, node_index) RNG. The
    branch angle is hard-clamped to [0°, 90°] after jitter to avoid inverted
    or perpendicular-to-self branches.
    """
    g = np.asarray(growth_direction, dtype=np.float64)
    g = g / np.linalg.norm(g)
    right, up = _frame_perpendicular_to(g)

    if cfg.mode == "alternate":
        k = 1
    elif cfg.mode == "opposite":
        k = 2
    elif cfg.mode == "whorled":
        k = max(1, cfg.whorl_count)
    else:
        raise ValueError(f"unknown phyllotaxy mode: {cfg.mode!r}")

    base_azimuth = math.radians(cfg.divergence_angle_deg) * node_index
    branch_angle = math.radians(cfg.branch_angle_deg)

    if cfg.divergence_jitter_deg > 0 or cfg.branch_angle_jitter_deg > 0:
        ss = np.random.SeedSequence([seed, _PHYLLO_SALT, node_index])
        rng = np.random.default_rng(ss.generate_state(1)[0])
        if cfg.divergence_jitter_deg > 0:
            base_azimuth += math.radians(rng.normal(0.0, cfg.divergence_jitter_deg))
        if cfg.branch_angle_jitter_deg > 0:
            branch_angle += math.radians(rng.normal(0.0, cfg.branch_angle_jitter_deg))
            branch_angle = max(0.0, min(math.pi / 2, branch_angle))

    cos_b = math.cos(branch_angle)
    sin_b = math.sin(branch_angle)

    out = np.empty((k, 3), dtype=np.float64)
    for i in range(k):
        az = base_azimuth + 2.0 * math.pi * i / k
        radial = math.cos(az) * right + math.sin(az) * up
        out[i] = cos_b * g + sin_b * radial
    return out


# Salt for SeedSequence to namespace phyllotaxy jitter independently of other
# RNG consumers (light_perception, internode_length jitter).
_PHYLLO_SALT = int.from_bytes(b"phyl", "big")


def _frame_perpendicular_to(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return any (right, up) orthonormal basis perpendicular to unit vector d."""
    canonical = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    right = canonical - np.dot(canonical, d) * d
    right = right / np.linalg.norm(right)
    up = np.cross(d, right)
    return right, up
```

Note technique : `SeedSequence([seed, "phyllotaxy", node_index])` n'est pas accepté (les éléments doivent être des entiers). On encode `"phyl"` en bytes puis en int comme "sel" (`_PHYLLO_SALT`). Idem pour les autres call sites RNG.

- [ ] **Step 6 : Mettre à jour le call site dans `simulator.py`**

Dans `src/palubicki/sim/simulator.py`, ligne ~217 actuellement :

```python
                lateral_dirs = lateral_bud_directions(d, cfg.phyllotaxy, node_index=state.node_index)
```

Remplace par :

```python
                lateral_dirs = lateral_bud_directions(
                    d, cfg.phyllotaxy,
                    node_index=state.node_index,
                    seed=cfg.seed,
                )
```

- [ ] **Step 7 : Exécuter `test_phyllotaxy.py`**

```bash
.venv/bin/pytest tests/sim/test_phyllotaxy.py -v 2>&1 | tail -30
```

Expected: tous PASS, y compris les 4 nouveaux tests.

- [ ] **Step 8 : Exécuter `test_config_species.py` partiellement**

Les YAML de la Tâche 3 référencent `divergence_jitter_deg` qui existe désormais. Mais ils référencent aussi `internode_length_jitter` qui n'existe **toujours pas**. Vérifier :

```bash
.venv/bin/pytest tests/test_config_species.py -v 2>&1 | tail -10
```

Expected: encore FAIL avec `unknown keys in section 'sim': ['internode_length_jitter']`. On corrige en Tâche 5.

- [ ] **Step 9 : Commit (phyllotaxy seul, pas encore les presets)**

```bash
git add src/palubicki/config.py src/palubicki/sim/phyllotaxy.py src/palubicki/sim/simulator.py tests/sim/test_phyllotaxy.py
git commit -m "$(cat <<'EOF'
feat(phyllotaxy): gaussian jitter on divergence + branch angles

Adds divergence_jitter_deg and branch_angle_jitter_deg to PhyllotaxyConfig.
lateral_bud_directions takes a seed: int; jitter is deterministic per
(seed, node_index). branch_angle clamped to [0°, 90°] post-jitter.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 : Ajouter `internode_length_jitter`

**Files:**
- Modify: `src/palubicki/config.py` (SimConfig + validation)
- Modify: `src/palubicki/sim/simulator.py` (calcul du length par substep)
- Modify: `tests/sim/test_simulator.py` (nouveaux tests)
- Modify: `tests/test_config.py` (test de validation du cap 0.5)

- [ ] **Step 1 : Écrire le test de validation**

Dans `tests/test_config.py`, ajoute :

```python
def test_config_rejects_internode_length_jitter_above_cap(tmp_path):
    with pytest.raises(ConfigError, match="internode_length_jitter"):
        _make_config(
            sim=SimConfig(internode_length_jitter=0.6),
            output=tmp_path / "out.glb",
        )


def test_config_rejects_negative_internode_length_jitter(tmp_path):
    with pytest.raises(ConfigError, match="internode_length_jitter"):
        _make_config(
            sim=SimConfig(internode_length_jitter=-0.05),
            output=tmp_path / "out.glb",
        )
```

- [ ] **Step 2 : Écrire les tests fonctionnels du jitter d'internode_length**

Dans `tests/sim/test_simulator.py`, ajoute (à la fin du fichier) :

```python
def test_internode_length_jitter_disabled_keeps_constant_length():
    """With jitter=0, all internode lengths equal cfg.sim.internode_length exactly."""
    from palubicki.config import (
        Config, EnvelopeConfig, GeomConfig, LightConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate
    cfg = Config(
        envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=300),
        sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1,
                      internode_length_jitter=0.0, max_iterations=6),
        tropism=TropismConfig(),
        phyllotaxy=PhyllotaxyConfig(),
        shedding=SheddingConfig(enabled=False),
        geom=GeomConfig(),
        light=LightConfig(enabled=False),
        seed=7,
        output=Path("/tmp/_pj_dummy.glb"),
    )
    tree = simulate(cfg)
    lengths = {round(iod.length, 9) for iod in tree.all_internodes}
    assert lengths == {0.1}, f"expected only 0.1, got {sorted(lengths)}"


def test_internode_length_jitter_deterministic_with_seed():
    """Same seed → same internode length sequence."""
    from palubicki.config import (
        Config, EnvelopeConfig, GeomConfig, LightConfig, PhyllotaxyConfig,
        SheddingConfig, SimConfig, TropismConfig,
    )
    from palubicki.sim.simulator import simulate

    def run(seed):
        cfg = Config(
            envelope=EnvelopeConfig(shape="ellipsoid", rx=0.7, ry=1.4, rz=0.7, marker_count=300),
            sim=SimConfig(r_perception=0.4, r_kill=0.12, internode_length=0.1,
                          internode_length_jitter=0.15, max_iterations=6),
            tropism=TropismConfig(),
            phyllotaxy=PhyllotaxyConfig(),
            shedding=SheddingConfig(enabled=False),
            geom=GeomConfig(),
            light=LightConfig(enabled=False),
            seed=seed,
            output=Path("/tmp/_pj_dummy.glb"),
        )
        tree = simulate(cfg)
        return [iod.length for iod in tree.all_internodes]

    a = run(7)
    b = run(7)
    assert a == b

    c = run(8)
    assert a != c
    # Mean should be close to internode_length on a sufficient sample
    import statistics
    assert len(a) > 5
    assert abs(statistics.mean(a) - 0.1) < 0.05
```

Note : la ligne `from pathlib import Path` doit déjà être importée en haut du fichier — vérifie et ajoute-la si besoin.

- [ ] **Step 3 : Exécuter, vérifier l'échec**

```bash
.venv/bin/pytest tests/test_config.py::test_config_rejects_internode_length_jitter_above_cap tests/test_config.py::test_config_rejects_negative_internode_length_jitter tests/sim/test_simulator.py::test_internode_length_jitter_disabled_keeps_constant_length tests/sim/test_simulator.py::test_internode_length_jitter_deterministic_with_seed -v
```

Expected: FAIL avec `SimConfig() got unexpected keyword 'internode_length_jitter'`.

- [ ] **Step 4 : Ajouter le champ à `SimConfig`**

Dans `src/palubicki/config.py`, dans `SimConfig` (autour de la ligne 48), ajoute après `n_substeps_max: int = field(...)` :

```python
    # Gaussian jitter (σ as a fraction of internode_length) applied per new
    # internode. 0.0 = exact constant length; 0.10-0.15 = realistic variability.
    # The drawn factor is clamped to [0.5, 1.5] regardless of σ.
    internode_length_jitter: float = field(
        default=0.0, metadata={"ui": {"min": 0.0, "max": 0.5, "step": 0.01}}
    )
```

- [ ] **Step 5 : Ajouter la validation**

Dans `Config.__post_init__`, à proximité de la validation `s.internode_length > 0` (ligne ~221), insère :

```python
        if not (0.0 <= s.internode_length_jitter <= 0.5):
            raise ConfigError(
                f"sim.internode_length_jitter must be in [0, 0.5], got {s.internode_length_jitter}"
            )
```

- [ ] **Step 6 : Modifier le calcul de length dans `simulator.py`**

Dans `src/palubicki/sim/simulator.py`, le passage ligne 182-208 (la création de l'Internode) doit calculer une longueur jittered. Remplace :

```python
                new_pos = cur.position + d * cfg.sim.internode_length

                # V3: obstacle blocking
                if forest.obstacles:
                    from palubicki.sim.obstacles import segment_blocked, any_contains
                    if segment_blocked(cur.position, new_pos, forest.obstacles):
                        cur.state = BudState.DORMANT
                        new_active.append(cur)
                        chain.done = True
                        continue
                    if any_contains(new_pos, forest.obstacles):
                        cur.state = BudState.DEAD
                        chain.done = True
                        continue

                new_node = Node(position=new_pos)
                iod = Internode(
                    parent_node=cur.parent_node,
                    child_node=new_node,
                    length=cfg.sim.internode_length,
                    is_main_axis=is_main,
                    window=cfg.shedding.window,
                )
```

Par :

```python
                length = cfg.sim.internode_length
                if cfg.sim.internode_length_jitter > 0:
                    ss = np.random.SeedSequence(
                        [cfg.seed, _ILEN_SALT, iteration, state.node_index]
                    )
                    rng = np.random.default_rng(ss.generate_state(1)[0])
                    factor = max(0.5, min(1.5, rng.normal(1.0, cfg.sim.internode_length_jitter)))
                    length = cfg.sim.internode_length * factor
                new_pos = cur.position + d * length

                # V3: obstacle blocking
                if forest.obstacles:
                    from palubicki.sim.obstacles import segment_blocked, any_contains
                    if segment_blocked(cur.position, new_pos, forest.obstacles):
                        cur.state = BudState.DORMANT
                        new_active.append(cur)
                        chain.done = True
                        continue
                    if any_contains(new_pos, forest.obstacles):
                        cur.state = BudState.DEAD
                        chain.done = True
                        continue

                new_node = Node(position=new_pos)
                iod = Internode(
                    parent_node=cur.parent_node,
                    child_node=new_node,
                    length=length,
                    is_main_axis=is_main,
                    window=cfg.shedding.window,
                )
```

Et ajoute en haut du fichier (proche des imports), après l'import `np` :

```python
_ILEN_SALT = int.from_bytes(b"ilen", "big")
```

- [ ] **Step 7 : Exécuter la suite complète sauf goldens**

```bash
.venv/bin/pytest --ignore=tests/golden -v 2>&1 | tail -30
```

Expected: tout PASS. Si quelque chose casse (notamment `test_config_species.py`), inspecter et corriger.

- [ ] **Step 8 : Commit (presets + nouveau champ + tests)**

```bash
git add src/palubicki/config.py src/palubicki/sim/simulator.py \
        src/palubicki/configs/species/oak.yaml \
        src/palubicki/configs/species/pine.yaml \
        src/palubicki/configs/species/birch.yaml \
        tests/test_config.py tests/test_config_species.py tests/test_config_yaml.py \
        tests/sim/test_simulator.py
git commit -m "$(cat <<'EOF'
feat(sim): internode_length_jitter + rewrite presets with new fields

Adds SimConfig.internode_length_jitter (σ as fraction, gaussian, clamped
[0.5, 1.5]). Rewrites oak/pine/birch YAML presets to use w_orthotropy_main/
_lateral, w_gravitropism_main/_lateral, divergence_jitter_deg,
branch_angle_jitter_deg, internode_length_jitter. Birch sag attenuated
since w_gravitropism_lateral now carries the pendula effect directly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6 : Régénérer les goldens et validation visuelle

**Files:**
- Modify: `tests/golden/data/*.sha256` (régénéré)
- Modify: `tests/golden/test_goldens.py` (la valeur `EXPECTED` du forest hash, ligne 154)

- [ ] **Step 1 : Faire tourner toute la suite, voir lesquels goldens échouent**

```bash
.venv/bin/pytest tests/golden -v 2>&1 | tail -20
```

Expected: au moins `test_golden_ellipsoid`, `test_golden_ellipsoid_light`, `test_golden_forest_v3`, et les 3 `test_species_golden[oak|pine|birch]` échouent par hash mismatch.

- [ ] **Step 2 : Régénérer les SHA256 hashes**

```bash
.venv/bin/pytest tests/golden --update-goldens 2>&1 | tail -20
```

Expected: les tests sont marqués `SKIPPED` ("golden written") — les fichiers `.sha256` sont mis à jour.

- [ ] **Step 3 : Mettre à jour la valeur en dur du forest hash**

`test_golden_forest_v3` (lignes 114-157) compare contre une constante `EXPECTED` codée en dur. Repérer la valeur produite par la run précédente :

```bash
.venv/bin/pytest tests/golden/test_goldens.py::test_golden_forest_v3 -v -s 2>&1 | grep "V3 forest golden hash"
```

Expected: une ligne `V3 forest golden hash: <new_hash>`.

Édite `tests/golden/test_goldens.py` ligne 154 :

```python
    EXPECTED = "<paste new hash here>"
```

- [ ] **Step 4 : Re-run tests/golden au complet**

```bash
.venv/bin/pytest tests/golden -v 2>&1 | tail -15
```

Expected: tous PASS.

- [ ] **Step 5 : Run la suite complète**

```bash
.venv/bin/pytest 2>&1 | tail -10
```

Expected: 100% pass.

- [ ] **Step 6 : Validation visuelle manuelle (CHECKPOINT)**

**Important** : avant le commit final, l'utilisateur doit valider visuellement les trois presets. Lui suggérer :

```bash
.venv/bin/palubicki edit
```

Ouvrir `palubicki edit`, charger chaque preset (`oak`, `pine`, `birch`), inspecter dans le viewer 3D. Critères qualitatifs (cf spec §7.3) :
- **Chêne** : primaires plus horizontaux qu'avant, divergence azimutale moins régulière.
- **Pin** : verticilles toujours nets, latéraux peu inclinés (presque plats).
- **Bouleau** : effet pleureur visible via `w_gravitropism_lateral=0.15` plus que via sag (sag atténué).

Si la validation visuelle révèle un comportement non souhaité, **NE PAS commit** : ajuster les valeurs dans les presets et reprendre à Step 1 de cette tâche.

- [ ] **Step 7 : Commit (goldens + screenshot éventuel)**

```bash
git add tests/golden/data tests/golden/test_goldens.py
git commit -m "$(cat <<'EOF'
test(golden): regenerate goldens after Phase 1 realism foundations

Hashes diverge due to: main/lateral tropism split, phyllotaxy jitter,
internode_length jitter, and preset rewrites. Visually validated for the
3 species presets before commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Done criteria

- [ ] `pytest` passe à 100% (suite complète, goldens inclus).
- [ ] Validation visuelle des 3 presets effectuée (cf Task 6 Step 6).
- [ ] Diff YAML cohérent : aucun champ legacy (`w_orthotropy`, `w_gravitropism`, `w_gravity`) ne subsiste dans les sources ou les tests.
- [ ] `_apply_section_aliases` supprimé de `config.py`.
- [ ] `palubicki edit` expose les nouveaux sliders (vérifier en chargeant l'UI).

## Hors scope (rappel de la spec)

- Pas de modification de `shedding.py` (Phase 2+ si besoin).
- Pas d'angle d'insertion âge-dépendant (Phase 2).
- Pas de tropisme par poids (Phase 2).
- Pas de croissance préformée, réitération, alpha_basipetal âge-dépendant (Phase 3).
- Pas de phyllotaxie au niveau feuille (Phase 4).
- Pas de métriques de fractalité (Phase 5).
- Le sag du bouleau reste activé (atténué) — sa suppression viendra en Phase 2.
