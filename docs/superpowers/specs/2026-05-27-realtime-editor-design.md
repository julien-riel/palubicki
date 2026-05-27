# Real-time tree parameter editor — design

**Date** : 2026-05-27
**Status** : design approved, pending implementation plan

## Goal

Permettre d'éditer les paramètres de simulation d'un arbre et de visualiser le résultat en 3D, depuis un navigateur web, sans relancer la CLI à chaque itération.

## Scope

**In scope** :
- Single tree (un seul arbre par session d'édition).
- Sélecteur d'espèce (oak / pine / birch) qui pré-remplit les sliders.
- Sliders/inputs pour les paramètres simulation, geometry, light, sag, phyllotaxy, shedding, tropism, envelope.
- Modèle d'interaction : l'utilisateur modifie les paramètres puis clique **Régénérer** ; la simulation tourne (1–5s typique) et le nouveau mesh remplace l'ancien dans le viewer.
- Export `.glb` (download du mesh courant).
- Export YAML config (download, compatible avec `palubicki generate --config`).
- Toggle leaves on/off, toggle wireframe.
- Démarrage : `palubicki edit [--config PATH] [--species NAME] [--port N] [--no-browser]`.

**Out of scope (MVP)** :
- Forest multi-arbres.
- Obstacles.
- Auto-régénération live (debounce).
- Édition de textures (`leaf_texture`, `bark_texture`).
- Comparaison côte-à-côte / historique d'arbres.
- Cancel d'une simulation en cours.
- Multi-utilisateur, authentification.
- Animation iteration-par-iteration.

## Architecture

Trois composants :

```
┌───────────────────────────────┐         ┌───────────────────────────┐
│  Browser (127.0.0.1:8765/)    │  HTTP   │  uvicorn / FastAPI         │
│  - three.js viewer            │ ◄─────► │  - GET  /                  │
│  - sliders auto-générés       │         │  - GET  /static/*          │
│  - dropdown espèce            │         │  - GET  /api/schema        │
│  - boutons Régénérer / Export │         │  - GET  /api/initial       │
└───────────────────────────────┘         │  - POST /api/species/{n}   │
                                          │  - POST /api/generate      │
                                          │  - POST /api/save-yaml     │
                                          └─────────────┬─────────────┘
                                                        │
                                                        ▼
                                          ┌───────────────────────────┐
                                          │  palubicki (existant)     │
                                          │  - load_config()          │
                                          │  - simulate()             │
                                          │  - build_mesh()           │
                                          │  - write_glb_to_bytes()   │
                                          └───────────────────────────┘
```

**Process model** : un seul process Python lancé par `palubicki edit`. uvicorn écoute sur `127.0.0.1` (jamais `0.0.0.0` — outil local mono-user, pas d'auth). Ouvre automatiquement le navigateur sur `http://127.0.0.1:<port>/` au démarrage (sauf `--no-browser`). Ctrl-C arrête.

**Concurrency** : `simulate()` est CPU-bound (quelques secondes). Exécutée dans un thread via `asyncio.to_thread()` pour ne pas bloquer le event loop FastAPI. Pas de pool — mono-user. Si un second `POST /api/generate` arrive pendant qu'un autre tourne, FastAPI les enqueue séquentiellement.

**Code layout** :
```
src/palubicki/
  edit/                       <- NOUVEAU
    __init__.py
    server.py                 # FastAPI app, endpoints
    schema.py                 # introspection des dataclasses → JSON schema
    static/
      index.html
      app.js
      style.css
      vendor/
        three.min.js
        GLTFLoader.js
        OrbitControls.js
  config.py                   # MODIF : ajouter metadata UI sur les fields exposés
  export/gltf.py              # MODIF : extraire write_glb_to_bytes()
  cli.py                      # MODIF : ajouter sous-commande `edit`
pyproject.toml                # MODIF : extra [edit] = {fastapi, uvicorn}
tests/
  edit/                       <- NOUVEAU
    test_schema.py
    test_server.py
```

Aucune modification aux modules `sim/`, `geom/`, `render/`, ni à la logique de `config.py` au-delà des metadata.

## Schema introspection

L'UI génère sliders/inputs à partir d'un JSON décrivant les dataclasses `Config`. Source de vérité : `field(metadata={"ui": ...})` sur chaque champ exposé.

**Exemple** (dans `config.py`) :
```python
@dataclass(frozen=True)
class SimConfig:
    r_perception: float = field(
        default=0.6,
        metadata={"ui": {"min": 0.1, "max": 3.0, "step": 0.05}},
    )
    max_iterations: int = field(
        default=30,
        metadata={"ui": {"min": 1, "max": 80, "step": 1}},
    )
    re_perceive_per_substep: bool = field(
        default=True,
        metadata={"ui": {"label": "Re-perceive per substep"}},
    )
```

**Règle d'exposition** : un champ apparaît dans l'UI **si et seulement si** il a `metadata["ui"]`. C'est un opt-in explicite. Permet d'omettre `output`, `log_level`, ou des champs avancés qu'on ne veut pas dans l'UI MVP.

**Types pris en charge par `build_schema()`** :

| Type Python | Sortie schema | Rendu UI |
|---|---|---|
| `int`, `float` | `{"type": "int"/"float", "min": ..., "max": ..., "step": ...}` | slider + input numérique |
| `bool` | `{"type": "bool"}` | checkbox |
| `Literal["a", "b"]` | `{"type": "enum", "choices": [...]}` | `<select>` |
| `tuple[float, float, float]` | `{"type": "vec3", "min": ..., "max": ..., "step": ...}` | 3 inputs numériques côte à côte |
| `Path \| None`, `dict`, structures complexes | omis du MVP | — |

**Format de `GET /api/schema`** :
```json
{
  "sections": [
    {
      "name": "envelope",
      "label": "Envelope",
      "fields": [
        {"name": "shape", "type": "enum", "default": "ellipsoid",
         "choices": ["sphere", "ellipsoid", "cone", "half_ellipsoid"]},
        {"name": "rx", "type": "float", "default": 1.0,
         "min": 0.5, "max": 20.0, "step": 0.1},
        ...
      ]
    },
    ...
  ],
  "species": ["birch", "oak", "pine"]
}
```

L'ordre des sections suit l'ordre déclaré dans `Config` (envelope, sim, tropism, phyllotaxy, shedding, geom, light, sag). L'ordre des fields suit l'ordre déclaré dans chaque dataclass.

**Ranges sensibles** : la valeur exacte de chaque `min/max/step` sera fixée à l'implémentation, basée sur les exemples du README, des presets d'espèces packagés, et le bon sens (e.g. `marker_count: 1000..100000 step 1000`, `r_kill: 0.01..1.0 step 0.01`).

## Backend API

| Méthode | Path | Request | Response | Rôle |
|---|---|---|---|---|
| `GET` | `/` | — | `text/html` | Page principale de l'éditeur |
| `GET` | `/static/{path}` | — | JS/CSS/vendor | Statique |
| `GET` | `/api/schema` | — | `application/json` | Schema introspection + liste espèces |
| `GET` | `/api/initial` | — | `application/json` | Config initiale (CLI flags ou defaults) |
| `POST` | `/api/species/{name}` | — | `application/json` | Config du preset (oak / pine / birch) |
| `POST` | `/api/generate` | JSON config | `application/octet-stream` (.glb) | Régénère et renvoie le mesh |
| `POST` | `/api/save-yaml` | JSON config | `application/x-yaml` | Sérialise la config (download) |

**Format JSON config échangé** : dict imbriqué identique à la sortie de `palubicki dump-defaults` (sections : `envelope`, `sim`, `tropism`, `phyllotaxy`, `shedding`, `geom`, `light`, `sag`, plus top-level `seed`). Permet de réutiliser `load_config()` directement.

**`POST /api/generate` flow** :
1. Parse JSON config.
2. `cfg = load_config(yaml_path=None, cli_overrides=<aplati>, output=Path("tree.glb"))`. Si `ConfigError` → `400 {"error": "<message>"}`.
3. `tree = await asyncio.to_thread(simulate, cfg)`.
4. `mesh = build_mesh(tree, cfg)`.
5. `data = write_glb_to_bytes(mesh, asset_meta={...})`.
6. Renvoie les bytes avec `Content-Type: model/gltf-binary`.

**Refactor `export/gltf.py`** : extraire `write_glb_to_bytes(mesh, asset_meta=...) -> bytes` de `write_glb(mesh, path, asset_meta=...)`. La fonction existante devient :
```python
def write_glb(mesh, path, asset_meta=None):
    data = write_glb_to_bytes(mesh, asset_meta=asset_meta)
    path.write_bytes(data)
```
Bénéfice secondaire : tests d'export devenant testables sans toucher au disque.

**`POST /api/save-yaml` flow** : même flow jusqu'à `cfg`, puis renvoie `yaml.safe_dump(_config_to_dict(cfg))` avec `Content-Disposition: attachment; filename=tree.yaml`.

**Logging** : niveau INFO par défaut. Chaque `POST /api/generate` logge `generated in <s>, <n> triangles`. Erreurs en WARNING avec stacktrace.

## Frontend

**Stack** :
- Vanilla HTML + JS, pas de framework, pas de TypeScript, pas de build step.
- three.js (~0.16x) vendored sous `static/vendor/` : `three.min.js`, `GLTFLoader.js`, `OrbitControls.js`. ~500 KB total. Vendor (pas CDN) pour fonctionner offline.
- `<script type="importmap">` pour résoudre les imports three.js.

**Layout** :
```
┌──────────────────────────────────────────────────────────────┐
│  palubicki edit                          [Régénérer] [▼ oak]  │
├────────────────────────────┬─────────────────────────────────┤
│  ▼ Envelope                │                                  │
│    shape    [ellipsoid ▼]  │                                  │
│    rx       [─●──] 3.0     │                                  │
│    ...                     │     three.js viewer              │
│  ▶ Sim                     │     (OrbitControls)              │
│  ▶ Tropism                 │                                  │
│  ▶ Phyllotaxy              │                                  │
│  ▶ Shedding                │                                  │
│  ▶ Geom                    │                                  │
│  ▶ Light                   │                                  │
│  ▶ Sag                     │                                  │
│  seed       [42]           │                                  │
│  [Export .glb] [Export YAML]│  [Toggle leaves] [Wireframe]    │
└────────────────────────────┴─────────────────────────────────┘
```

Sidebar gauche : sections en accordéon. Vue 3D : ~70% de la largeur de la fenêtre. Background gris clair (`#e8e8e8`). Lumière hémisphérique + une directionnelle. `OrbitControls` avec damping.

**Lifecycle au chargement** :
1. `GET /api/schema` → construction des accordéons + sliders.
2. `GET /api/initial` → remplissage des valeurs initiales.
3. `POST /api/generate` avec cette config → charge le .glb initial.

**Lifecycle au clic « Régénérer »** :
1. Collecte les valeurs des sliders → construit le JSON config.
2. Disable le bouton, affiche un spinner.
3. `POST /api/generate` → reçoit `ArrayBuffer`.
4. `GLTFLoader.parse(arrayBuffer, '', onLoad, onError)`.
5. Remplace le mesh courant dans la scène, dispose `geometry` et `material` de l'ancien (évite la fuite GPU).
6. Auto-fit la caméra sur la bbox du nouveau mesh.
7. Re-enable le bouton.

**Lifecycle au changement d'espèce** :
1. `POST /api/species/<name>` → reçoit la config preset.
2. Met à jour les valeurs des sliders dans l'UI.
3. **Ne régénère pas automatiquement** — l'utilisateur clique « Régénérer » quand prêt.

**Toggle leaves** : parcourt la scène three.js, masque (`visible = false`) les meshes dont le `material.name` contient `"leaf"` (le nom est défini dans `geom/builder.py` ; à confirmer à l'implémentation).

**Toggle wireframe** : sur tous les meshes, set `material.wireframe = true/false`.

**Export .glb** : bouton qui ré-utilise le dernier `ArrayBuffer` reçu de `/api/generate`, déclenche un download via un `<a>` invisible avec `download="tree.glb"`. Pas de second appel API nécessaire.

**Export YAML** : `POST /api/save-yaml` avec la config courante, déclenche un download via `Content-Disposition: attachment`.

**Validation côté UI** : minimaliste — `<input type="number">` respecte `min/max/step` du schema. Erreurs de cohérence (config invalide) gérées par le backend via `ConfigError`.

## CLI

**Sous-commande** : `palubicki edit`

```
palubicki edit [--config PATH] [--species {oak,pine,birch}] [--port N] [--no-browser]
```

| Flag | Défaut | Rôle |
|---|---|---|
| `--config` | `None` | YAML de départ |
| `--species` | `None` | Preset de départ |
| `--port` | `8765` | Port d'écoute (essaie `port..port+10` si occupé) |
| `--no-browser` | `False` | Ne pas ouvrir le browser automatiquement |

**Precedence** (comme `generate`) : `--config` > `--species` > defaults.

**Démarrage** :
1. Parse les flags.
2. Construit la config initiale via `load_config(yaml_path=args.config, cli_overrides={}, output=Path("tree.glb"), species=args.species)`. Si erreur → exit 2.
3. Stocke la config dans une variable module (lue par `/api/initial`).
4. Trouve un port disponible (scan `port..port+10`).
5. Lance un thread daemon qui attend 0.5s puis ouvre le browser via `webbrowser.open()` (sauf `--no-browser`).
6. `uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")` (bloquant).
7. Ctrl-C → shutdown propre uvicorn.

**Dépendances** :
- Nouvel extra dans `pyproject.toml` : `[edit] = ["fastapi>=0.110", "uvicorn[standard]>=0.27"]`.
- Si l'extra n'est pas installé, `palubicki edit` détecte l'`ImportError` sur `fastapi` au début du handler, et renvoie : `palubicki edit requires the [edit] extra. Run: pip install -e ".[edit]"` puis exit 2.
- PyYAML déjà présent.

## Error handling

### Backend

| Source | Réponse |
|---|---|
| `ConfigError` (config invalide) | `400 {"error": "<message>"}` |
| `ExportError` | `500 {"error": "<message>"}`, log stacktrace |
| Exception inattendue | `500 {"error": "<type>: <message>"}`, log stacktrace |
| `--config` YAML invalide au démarrage CLI | exit 2 stderr |
| Port occupé après 10 essais | exit 1 stderr |
| `fastapi`/`uvicorn` manquants | exit 2 avec instruction d'install |

Pas de validation custom de la config JSON au-delà de `load_config` — `ConfigError` est le filet de sécurité existant.

### Frontend

| Source | UI |
|---|---|
| `400` de `/api/generate` | Toast rouge bas-centre, arbre précédent conservé, bouton réactivé |
| `500` | Toast rouge "Erreur interne, voir terminal" |
| Erreur réseau (serveur tué) | Toast "Connexion perdue" |
| `GLTFLoader.parse` lève | Toast "Mesh invalide", garde l'ancien |
| `/api/schema` ou `/api/initial` échoue au load | Banner pleine largeur "Échec d'initialisation : <message>", l'UI ne se construit pas |

Toasts : auto-dismiss à 5s, cliquables pour fermer.

### Explicitement non géré (MVP)
- Cancel d'une simulation en cours.
- Plusieurs onglets simultanés : pas d'état partagé, chacun a sa propre copie de config ; les requêtes sont séquentialisées par FastAPI.

## Testing

**Unit — `tests/edit/test_schema.py`** :
- `build_schema()` retourne les sections dans l'ordre déclaré.
- Un field avec metadata `ui` apparaît avec les bonnes valeurs.
- Un field sans metadata `ui` est omis.
- `Literal[...]` produit `{"type": "enum", "choices": [...]}`.
- `tuple[float, float, float]` produit `{"type": "vec3", ...}`.
- `bool` produit `{"type": "bool"}`.
- La liste `species` correspond à `_list_species()`.

**Unit — `tests/export/test_gltf.py`** (à étendre) :
- `write_glb_to_bytes(mesh)` retourne `bytes` commençant par `b"glTF"`.
- `write_glb(path, mesh)` produit le même contenu qu'écrire `write_glb_to_bytes(mesh)`.

**Integration — `tests/edit/test_server.py`** (avec `fastapi.testclient.TestClient`) :
- `GET /api/schema` → 200, JSON contient `sections` et `species`.
- `GET /api/initial` → 200, JSON est une config valide.
- `POST /api/generate` avec config minimale (marker_count=200, max_iterations=3) → 200, `Content-Type: model/gltf-binary`, body commence par `b"glTF"`.
- `POST /api/generate` avec config invalide (e.g. `envelope.rx = -1`) → 400, JSON contient `error`.
- `POST /api/save-yaml` → 200, `Content-Type: application/x-yaml`, body parsable et accepté par `load_config`.
- `POST /api/species/oak` → 200, JSON correspond à `_load_packaged_species("oak")`.
- `POST /api/species/unknown` → 400 avec message.
- Initial config avec `--config` puis `--species` puis defaults : test la precedence.

**Smoke CLI — `tests/test_cli.py`** (à étendre, `@pytest.mark.slow`) :
- `palubicki edit --help` retourne 0 et liste les flags attendus.
- `palubicki edit --no-browser --port <éphémère>` démarre, répond 200 sur `/api/schema`, exit propre.

**Pas de tests Selenium / Playwright dans le MVP**. Test du frontend manuel pendant le développement, dans le navigateur. Si une régression frontend persistante apparaît, on ajoutera Playwright plus tard — pas le coût d'install/CI maintenant.

**Performance** : tous les tests `/api/generate` utilisent `marker_count=200, max_iterations=3` (sub-seconde). Une golden plus lourde `@pytest.mark.slow` vérifie qu'une config oak typique produit un .glb non-vide.

**Coverage cible** : >85% pour `src/palubicki/edit/`, maintien du global existant.

## Open questions for implementation

- Confirmer le nom exact du `material.name` pour les feuilles dans `geom/builder.py` (pour le toggle leaves).
- Fixer les `min/max/step` exacts de chaque field exposé — décidé champ par champ à l'implémentation, basé sur README, presets, et tests empiriques.
- Vérifier que three.js >= 0.16x parse correctement les `.glb` produits par `pygltflib` (probable mais à confirmer dans un test manuel en début d'implémentation).

## Risks

- **Performance perçue** : 1–5s de génération + transfert de quelques MB de mesh. Le spinner + désactivation du bouton doit suffire pour donner un feedback clair. Si la latence est inacceptable en pratique, V2 pourrait introduire un mode « live » pour les paramètres geom-only (taille feuille, couleur) qui n'exigent pas de re-simulation.
- **Fuite mémoire GPU côté three.js** si on oublie de `dispose()` les anciens meshes/textures/géométries à chaque régénération. Mitigation : helper `disposeScene(root)` clairement isolé, testé manuellement en regardant la mémoire GPU sur ~50 régénérations.
- **Drift entre dataclass et UI metadata** : un nouveau field sans metadata sera silencieusement absent de l'UI. Mitigation : pas de test automatique (c'est volontairement opt-in), mais ajouter une note dans `config.py` près des dataclasses : "Pour exposer un nouveau field dans l'éditeur, ajouter `metadata={'ui': {...}}`."
