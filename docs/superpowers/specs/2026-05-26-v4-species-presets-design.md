# V4 — Presets d'espèces (oak, pine, birch)

**Statut** : Spec
**Date** : 2026-05-26
**Préalable** : V3 obstacles + forêt livré et stable (commit `5233c04`).
**Référence papier** : Palubicki et al. 2009, Figure 12 (galerie d'espèces).

## Objectif

Livrer trois presets d'espèces (chêne, pin sylvestre, bouleau) reproduisant
qualitativement les silhouettes correspondantes de la Figure 12, **sans
modifier le moteur de simulation**. La valeur de V4 est dans l'infrastructure
(système de presets + textures procédurales + feuilles paramétriques) et dans
trois invocations CLI directes :

```bash
palubicki generate --species oak   --seed 42 -o oak.glb
palubicki generate --species pine  --seed 42 -o pine.glb
palubicki generate --species birch --seed 42 -o birch.glb
```

Quand `--species` est absent, V4 retombe sur V1/V2/V3 bit-exact (les goldens
existants ne bougent pas).

## Décisions de design

| Décision | Choix | Raison |
|---|---|---|
| Set d'espèces livrées | oak, pine, birch | Trois silhouettes visuellement distinctes (feuillu rond, conifère, feuillu fin) qui exercent toute l'infrastructure. Pommier / saule / frêne pleureur sortent du scope (voir Hors-scope). |
| Textures | Procédurales (PIL) par espèce | Pas de binaires dans le repo, déterministe (goldens stables), pas de question de licence. Le scheme `Path \| None` reste ouvert pour override PNG externe ensuite. |
| Forme des feuilles | Paramétrique : `leaf_cluster_count` + `leaf_aspect` + `leaf_splay_deg` | Une seule géométrie de feuille paramétrable couvre les 3 espèces (1 quad oak/birch, 5 aiguilles fines splayées pour pine). Plus simple qu'une primitive par espèce. |
| Résolution `--species` | YAML packagés dans `src/palubicki/configs/species/` via `importlib.resources` | Marche en pip install et en dev. Ajouter une espèce = déposer un YAML, pas de code. |
| Structure preset | YAML pur (pas de `SpeciesConfig` dataclass) | Un preset = juste un YAML pré-rempli. Pas de duplication des 8 sections existantes. Le YAML *est* l'interface. |
| Ordre de merge | preset YAML ← user `--config` ← CLI overrides | Preset = baseline, user surcharge, CLI gagne au final. Implémenté via un `_deep_merge` récursif dans `load_config`. |
| Bark texture | Nouveau champ `bark_texture: Path \| None` dans `GeomConfig` | Le pipeline export supporte déjà `base_color_texture_png` côté tubes (UV déjà émis), seul le builder passait `None` en dur. |
| Validation | Golden hash SHA-256 par espèce (`-m slow`) + smoke tests CLI | Conforme au pattern V1/V2/V3. Hashes pinés après gel visuel ; régénérables pendant tuning via `UPDATE_GOLDENS=1`. |
| Forêts mixtes | Champ optionnel `species: str` sur `ForestSeed` | Forêts oak+pine+birch deviennent triviales. ~15 lignes dans `per_tree_config`. |

## Architecture

### Modifications de `GeomConfig`

```python
# src/palubicki/config.py

@dataclass(frozen=True)
class GeomConfig:
    ring_sides: int = 8
    r_tip: float = 0.005
    pipe_exponent: float = 2.49
    leaf_size: float = 0.06
    leaf_texture: Path | None = None
    bark_color: tuple[float, float, float] = (0.35, 0.22, 0.12)
    bark_texture: Path | None = None              # NEW
    leaf_cluster_count: int = 1                   # NEW
    leaf_aspect: float = 1.0                      # NEW
    leaf_splay_deg: float = 0.0                   # NEW
    enable_leaves: bool = True
```

Validation `__post_init__` étendue :
- `leaf_cluster_count >= 1`
- `0 < leaf_aspect <= 4.0`
- `0 <= leaf_splay_deg <= 90`

Les défauts (`cluster_count=1, aspect=1.0, splay=0.0`) garantissent que
`_emit_leaf_cluster` se comporte **bit-exact** comme `_emit_cross_quad` actuel
→ goldens V1/V2/V3 inchangés.

### Générateurs de textures procéduraux

Fichier `geom/_leaf_texture.py` renommé en `geom/_textures.py`, contenant :

```python
def default_leaf_png(size: int = 128) -> bytes: ...   # conservé (rétro-compat)

# Bark — PNG tileable horizontalement (wrap autour des tubes)
def oak_bark_png(size: int = 256) -> bytes: ...       # gris-brun fissuré vertical
def pine_bark_png(size: int = 256) -> bytes: ...      # plaques ocre/rouge irrégulières
def birch_bark_png(size: int = 256) -> bytes: ...     # blanc cassé + stries horizontales

# Leaf — RGBA avec alpha mask
def oak_leaf_png(size: int = 128) -> bytes: ...       # lobé (8-10 lobes), vert moyen
def pine_needle_png(size: int = 128) -> bytes: ...    # aiguille fine, vert foncé
def birch_leaf_png(size: int = 128) -> bytes: ...     # triangle dentelé, vert clair

_PROC_TEXTURES = {
    "oak_bark": oak_bark_png,
    "pine_bark": pine_bark_png,
    "birch_bark": birch_bark_png,
    "oak_leaf": oak_leaf_png,
    "pine_needle": pine_needle_png,
    "birch_leaf": birch_leaf_png,
}
```

Toutes utilisent `PIL.ImageDraw` + `numpy` (pas de nouvelle dépendance). Toutes
déterministes pour un `size` donné (jitter via générateurs `random.Random(seed=...)`
locaux, pas de `np.random` global). Total estimé : ~200 lignes.

### Scheme `proc:` dans les chemins de texture

Le builder détecte le préfixe `proc:` au moment du chargement :

```python
# src/palubicki/geom/builder.py

def _resolve_texture(value) -> bytes | None:
    if value is None:
        return None
    s = str(value)
    if s.startswith("proc:"):
        name = s[5:]
        if name not in _PROC_TEXTURES:
            raise ConfigError(
                f"unknown proc texture: {name!r} (expected one of {sorted(_PROC_TEXTURES)})"
            )
        return _PROC_TEXTURES[name]()
    return Path(s).read_bytes()
```

Une seule clé YAML (`bark_texture` / `leaf_texture`), deux modes :
- `bark_texture: "proc:oak_bark"` → générateur procédural
- `bark_texture: "./my_bark.png"` → fichier disque

### Cluster de feuilles paramétrique

`geom/leaves.py` : `_emit_cross_quad` devient `_emit_leaf_cluster`.

Comportement :
- Pour chaque bourgeon terminal, émet `cluster_count` cross-quads.
- Chaque cross-quad est tourné de `(2π × i / cluster_count)` autour de la growth direction (rotation azimutale).
- Chaque cross-quad est ensuite incliné de `leaf_splay_deg` (tilt vers l'extérieur, perpendiculaire au growth direction).
- La largeur du quad est `leaf_size × leaf_aspect`, la hauteur reste `leaf_size`.

`cluster_count=1, splay=0, aspect=1` reproduit `_emit_cross_quad` exactement.

### Modifications `load_config`

```python
# src/palubicki/config.py

def load_config(
    *,
    yaml_path: Path | None,
    cli_overrides: dict,
    output: Path,
    species: str | None = None,                       # NEW
) -> Config:
    data: dict = {}
    if species is not None:
        data = _load_packaged_species(species)        # importlib.resources
    if yaml_path is not None:
        with open(yaml_path) as f:
            user = yaml.safe_load(f) or {}
        _deep_merge(data, user)                       # user wins, dict-deep
    for dotted, value in cli_overrides.items():
        _set_dotted(data, dotted, value)
    # ... reste inchangé (sections, validation, etc.) ...


def _load_packaged_species(name: str) -> dict:
    from importlib import resources
    try:
        text = resources.files("palubicki.configs.species").joinpath(f"{name}.yaml").read_text()
    except (FileNotFoundError, ModuleNotFoundError) as e:
        raise ConfigError(f"unknown species preset: {name!r}") from e
    return yaml.safe_load(text) or {}


def _deep_merge(base: dict, override: dict) -> None:
    """Merge override into base in-place. Recursive on dicts, replace on scalars/lists/tuples."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _list_species() -> list[str]:
    from importlib import resources
    files = resources.files("palubicki.configs.species").iterdir()
    return sorted(f.stem for f in files if f.name.endswith(".yaml"))
```

Le sous-package `src/palubicki/configs/species/` reçoit un `__init__.py` vide
pour devenir importable. `pyproject.toml` doit déjà inclure les fichiers data
du package (sinon : ajouter `include = ["palubicki.configs.species/*.yaml"]`).

### Modifications CLI

`cli.py` :
```python
g.add_argument("--species", choices=_list_species(), default=None,
               help="Load a packaged species preset (e.g. oak, pine, birch)")
```

Et dans `_cmd_generate` :
```python
cfg = load_config(
    yaml_path=args.config,
    cli_overrides=overrides,
    output=args.output,
    species=args.species,
)
```

`dump-defaults --species oak` (bonus) : imprime le YAML du preset packagé tel
quel via `_load_packaged_species("oak")` + `yaml.safe_dump`.

### Forêts mixtes (extension `ForestSeed`)

```python
# src/palubicki/config.py

@dataclass(frozen=True)
class ForestSeed:
    position: tuple[float, float, float]
    seed: int | None = None
    species: str | None = None                  # NEW
    overrides: dict = field(default_factory=dict)
```

Dans `per_tree_config` (sim/forest.py) : si `seed.species is not None`,
charger le preset packagé d'abord, puis appliquer `seed.overrides` par-dessus
via le même `_deep_merge`. Tout le reste reste inchangé.

## Contenu des trois presets

Les valeurs ci-dessous sont la **baseline de tuning** — elles seront affinées
visuellement pendant l'implémentation. Le critère final est qualitatif (œil
+ référence Figure 12), pas une métrique automatique.

### `configs/species/oak.yaml`

Quercus robur — dense, étalé, ramure tortueuse :

```yaml
envelope:
  shape: half_ellipsoid
  rx: 5.0
  ry: 6.5
  rz: 5.0
  marker_count: 25000
sim:
  internode_length: 0.12
  lambda_apical: 0.50
  alpha_basipetal: 2.2
  max_iterations: 35
tropism:
  w_gravity: 0.25
  w_phototropism: 0.35
  w_direction_inertia: 0.5
phyllotaxy:
  mode: alternate
  divergence_angle_deg: 137.5
  branch_angle_deg: 55
shedding:
  quality_threshold: 0.15
light:
  enabled: true
  k_absorption: 0.55
geom:
  ring_sides: 10
  pipe_exponent: 2.55
  bark_color: [0.32, 0.22, 0.14]
  bark_texture: "proc:oak_bark"
  leaf_texture: "proc:oak_leaf"
  leaf_size: 0.10
  leaf_cluster_count: 1
  leaf_aspect: 1.0
  leaf_splay_deg: 0
```

### `configs/species/pine.yaml`

Pinus sylvestris — conifère conique, étages réguliers, apical dominant :

```yaml
envelope:
  shape: cone
  rx: 2.5
  ry: 9.0
  rz: 2.5
  marker_count: 18000
sim:
  internode_length: 0.18
  lambda_apical: 0.85
  alpha_basipetal: 1.8
  max_iterations: 40
tropism:
  w_gravity: 0.15
  w_phototropism: 0.20
  w_direction_inertia: 0.8
phyllotaxy:
  mode: whorled
  whorl_count: 5
  divergence_angle_deg: 72
  branch_angle_deg: 75
shedding:
  quality_threshold: 0.20
light:
  enabled: true
  k_absorption: 0.65
geom:
  ring_sides: 8
  pipe_exponent: 2.45
  bark_color: [0.45, 0.25, 0.18]
  bark_texture: "proc:pine_bark"
  leaf_texture: "proc:pine_needle"
  leaf_size: 0.08
  leaf_cluster_count: 5
  leaf_aspect: 0.12
  leaf_splay_deg: 25
```

### `configs/species/birch.yaml`

Betula pendula — élancé, branches fines, port pleureur léger :

```yaml
envelope:
  shape: ellipsoid
  rx: 2.5
  ry: 7.0
  rz: 2.5
  marker_count: 20000
sim:
  internode_length: 0.10
  lambda_apical: 0.65
  alpha_basipetal: 2.0
  max_iterations: 32
tropism:
  w_gravity: 0.45
  w_phototropism: 0.30
  w_direction_inertia: 0.35
phyllotaxy:
  mode: alternate
  divergence_angle_deg: 137.5
  branch_angle_deg: 45
shedding:
  quality_threshold: 0.10
light:
  enabled: true
  k_absorption: 0.45
geom:
  ring_sides: 8
  pipe_exponent: 2.40
  r_tip: 0.004
  bark_color: [0.85, 0.82, 0.75]
  bark_texture: "proc:birch_bark"
  leaf_texture: "proc:birch_leaf"
  leaf_size: 0.07
  leaf_cluster_count: 2
  leaf_aspect: 0.7
  leaf_splay_deg: 15
```

**Note** : `seed`, `output`, `log_level` ne sont pas dans les presets — ce sont
des inputs runtime fournis à l'invocation. Les champs non-listés conservent
leurs défauts (un preset ne surcharge que ce qui caractérise vraiment l'espèce).

## Tests

### `tests/test_config_species.py` (unit)

- `test_list_species_finds_three` : `["birch", "oak", "pine"]`.
- `test_load_preset_oak` : `cfg.envelope.shape == "half_ellipsoid"`, `cfg.geom.leaf_cluster_count == 1`.
- `test_unknown_species_raises` : `species="redwood"` → `ConfigError`.
- `test_user_yaml_overrides_preset` : preset oak + `--config` avec `tropism.w_gravity: 0.99` → 0.99 final, autres champs oak intacts.
- `test_cli_override_wins_over_user_yaml` : preset + user YAML + CLI → CLI gagne.
- `test_deep_merge_preserves_sibling_sections` : user YAML touchant `tropism` seul ne doit pas effacer `envelope` ni `phyllotaxy` du preset.
- `test_proc_scheme_unknown_raises` : `bark_texture: "proc:nonexistent"` → `ConfigError` au moment du build.

### `tests/geom/test_textures.py` (unit)

- Pour chaque générateur : `len(png) > 0`, `Image.open(BytesIO(png)).size == (expected, expected)`, mode RGBA pour les leaves.
- `test_textures_deterministic` : appeler deux fois → bytes identiques.
- `test_leaf_textures_have_alpha` : oak/pine/birch leaves → mode RGBA.

### `tests/geom/test_leaf_cluster.py` (unit)

- `test_cluster_count_1_matches_v1_geometry` : défauts produisent géométrie bit-exact identique à `_emit_cross_quad` actuel (critique pour rétro-compat goldens V1/V2/V3).
- `test_cluster_count_5_emits_5x_vertices` : nb vertices par bourgeon = `cluster_count * 8`.
- `test_splay_angle_rotates_blades` : `splay_deg=30` → normales tournées de 30° autour de growth direction.
- `test_aspect_ratio_changes_width` : `leaf_aspect=0.2` → largeur quad = `0.2 * leaf_size`, hauteur inchangée.

### `tests/golden/test_species_goldens.py` (slow)

```python
@pytest.mark.slow
@pytest.mark.parametrize("species,expected_sha", [
    ("oak",   "<pinned_after_tuning>"),
    ("pine",  "<pinned_after_tuning>"),
    ("birch", "<pinned_after_tuning>"),
])
def test_species_golden(tmp_path, species, expected_sha):
    out = tmp_path / f"{species}.glb"
    assert main(["generate", "--species", species, "--seed", "42",
                 "-o", str(out)]) == 0
    assert hashlib.sha256(out.read_bytes()).hexdigest() == expected_sha
```

Mode `UPDATE_GOLDENS=1 pytest -m slow` régénère les hashes pendant le tuning.
Une fois le rendu visuel validé, les hashes sont gelés.

### `tests/test_cli.py` (smoke, étend l'existant)

- Pour chaque espèce : `palubicki generate --species <X>` produit un `.glb` chargeable par `pygltflib`, ≥2 primitives, bark texture présente dans `gltf.textures`.
- `test_species_with_user_config_override_runs` : combinaison `--species oak --config tweaks.yaml` → exit 0.
- `test_forest_with_species_per_seed` : YAML forest avec `species: oak` + `species: pine` → 2 arbres distincts.
- `test_dump_defaults_species_prints_yaml` : `dump-defaults --species oak` imprime du YAML parseable contenant `bark_texture: proc:oak_bark`.

## Workflow de tuning

Itératif et manuel — pas de métrique automatique pour "ressemble à un chêne".

1. Démarrer chaque preset avec les valeurs ci-dessus.
2. `palubicki generate --species oak --seed 42 -o out/oak.glb && open out/oak.glb`
   (Quick Look macOS gère `.glb`, ou drag-drop dans https://gltf-viewer.donmccurdy.com/ pour PBR correct).
3. Modifier `src/palubicki/configs/species/oak.yaml`, re-run, comparer.
4. Critères visuels par espèce :
   - **Oak** : silhouette ronde large, branches tortueuses étalées, feuillage dense en touffe.
   - **Pine** : cône, étages de branches horizontales bien marqués, flèche apicale visible.
   - **Birch** : silhouette élancée verticale, tronc clair, branches légèrement retombantes.
5. Quand satisfaisant : pin du golden hash via `UPDATE_GOLDENS=1`, commit, fin.

## Risques

| Risque | Probabilité | Mitigation |
|---|---|---|
| Textures procédurales PIL "moches" comparées à de vraies photos | Haute | Accepter — V4 valide l'architecture, pas un concours avec SpeedTree. Override PNG externe reste possible via `bark_texture: ./real.png`. |
| Tuning visuel plus long que prévu | Haute | Découpler livraison de tuning fin : V4 livre infra + 3 presets "raisonnables", affinages ultérieurs en patches incrémentaux. |
| `cluster_count=5` pour pine alourdit le .glb | Moyenne | Mesurer (~400k vertices estimés acceptables) ; fallback à 3 si trop lourd. |
| Bug subtil dans `_deep_merge` (tuples/listes/dicts) | Moyenne | Tests `test_user_yaml_overrides_preset` et `test_deep_merge_preserves_sibling_sections`. Règle stricte : récursif sur dicts, **remplacement** complet sur tout le reste. |
| Typo silencieuse dans `proc:nom_de_texture` | Faible | `_resolve_texture` lève `ConfigError` explicite avec liste des noms valides. |
| Rétro-compat brisée pour V1/V2/V3 | **Critique** | Test `test_cluster_count_1_matches_v1_geometry` garantit défauts = comportement bit-exact. Goldens V1/V2/V3 inchangés est un critère d'acceptation dur. |

## Hors-scope V4 (explicite)

- **Pommier, frêne pleureur, saule pleureur** — la roadmap les liste mais ils sortent du sous-set choisi. Le saule en particulier nécessite un tropisme négatif fort (plagiotropisme par poids) qui **n'existe pas dans V1+V2+V3**. À traiter dans une V5 "advanced tropisms".
- **Variabilité intra-espèce** : un seul preset par espèce, la diversité vient de `--seed`.
- **Animation de croissance / timelapse**.
- **Override texture par PNG externe** : signature le permet, pas de doc/test dédié.
- **Gallery markdown avec screenshots** : peut venir comme suivi léger.
- **Validation visuelle automatisée** (rendering offscreen, comparaison image) : trop d'infrastructure.

## Critères d'acceptation

1. `palubicki generate --species {oak,pine,birch} --seed 42 -o <name>.glb` produit un fichier `.glb` valide pour les trois espèces.
2. Les trois `.glb` ont des silhouettes visuellement distinctes (validation humaine).
3. Tous les tests V1/V2/V3 existants passent inchangés (goldens compris).
4. Les nouveaux tests unit + smoke passent.
5. Les goldens des 3 espèces sont pinés et reproductibles.
6. `palubicki forest --config <yaml_with_species_per_seed>` produit une forêt mixte oak+pine+birch fonctionnelle.
