# Render — sortie PNG headless depuis Mesh ou .glb

**Statut** : Spec
**Date** : 2026-05-26
**Préalable** : V4 (presets d'espèces) livré.
**Motivation** : aujourd'hui voir un arbre demande d'ouvrir un viewer externe sur le `.glb`. Friction énorme à l'itération (V4 presets, debug seeds, démos). Ce module ajoute un rendu PNG en CPU pur, sans display, utilisable sur Mac et Linux CI à l'identique.

## Objectif

Livrer un sous-paquet `palubicki.render` qui produit une image PNG **diagnostique** (silhouette + couleurs unies, Lambert flat) à partir d'un `Mesh` interne ou d'un `.glb` sur disque, sans contexte OpenGL, sans display, sans dépendance native. Plus une sous-commande CLI `palubicki preview tree.glb -o tree.png`.

Trois usages cibles :

1. **Itération locale** : `palubicki preview` remplace l'ouverture manuelle du `.glb` dans un viewer externe.
2. **Goldens visuels (artefact)** : quand un test golden échoue, un PNG `actual + expected` est généré dans `tmp_path/` pour comparer à l'œil, sans toucher aux asserts buffer-SHA existants.
3. **Notebooks** : `render_mesh(mesh)` retourne un `ndarray` directement affichable via `plt.imshow` ou `IPython.display.Image`.

Le module est volontairement contraint au niveau "diagnostic" (pas de textures, pas d'ombres, pas d'antialiasing avancé). Il existe pour rendre le développement supportable, pas pour produire des images de marketing.

## Décisions de design

| Décision | Choix | Raison |
|---|---|---|
| Backend de rendu | matplotlib `Poly3DCollection` (extra optionnel) | Zéro dépendance native, marche identiquement Mac + Linux CI sans display. ~150 LOC. Trade-off : painter's algo peut mal trier les chevauchements branches/feuilles — acceptable au niveau diagnostic. |
| Cible headless | macOS local + Linux CI, *vrai* headless | Élimine pyrender/trimesh.save_image (qui exigent un contexte GL). Mac n'a pas d'OSMesa/EGL standard. |
| Fidélité visuelle | Diagnostic (silhouette + base_color flat Lambert) | Suffit pour : voir qu'un arbre n'est pas dansant, comparer seeds, diff visuel en CI, image dans un notebook. Textures + alpha sortent du scope. |
| Stratégie goldens | PNG d'artefact seulement, asserts inchangés | Goldens actuels = SHA-256 sur buffers glTF, restent autoritatifs. PNG généré uniquement *sur échec* pour faciliter le diagnostic. Pas de risque de flakiness matplotlib en CI. |
| Format de sortie | `ndarray (H, W, 4) uint8` RGBA + helper `save_png` | API notebook-friendly. La CLI passe par `save_png` après render. |
| Dépendance matplotlib | Extra optionnel `palubicki[render]` | matplotlib + Pillow alourdiraient l'install par défaut. Les utilisateurs qui ne veulent que générer des `.glb` ne payent rien. |
| Convention axes | Y-up (cohérent avec `tropism.w_orthotropy`) | Pas de flag d'orientation. Le module documente la convention. |
| Auto-fit caméra | bbox concaténée de toutes les primitives + marge 8 % | Évite le clipping en bouts de branches, garde l'arbre centré. Marche identiquement pour un arbre seul et pour une forêt. |
| Forêts | Pas de cadrage par-arbre dans la CLI V1 | YAGNI. L'utilisateur qui veut zoomer extrait le sous-mesh côté code. |
| Logging | `logging.getLogger("palubicki.render")`, une seule ligne info à la fin | Pas de spam. Respecte `--log-level` global de la CLI. |

## Architecture

### Layout du sous-paquet

En miroir de `geom/`, `sim/`, `export/` :

```
src/palubicki/render/
├── __init__.py       # re-exporte render_mesh, render_glb, save_png, Camera + exceptions
├── camera.py         # dataclass Camera + Camera.fit(mesh)
├── renderer.py       # render_mesh() — le seul point d'entrée pipeline
└── io.py             # _glb_to_mesh() pour charger un .glb → Mesh + save_png()
```

Le module n'importe rien de `palubicki.sim` ni `palubicki.cli`. Dépendance unique : `palubicki.geom.mesh.Mesh`. Sens unique : `sim → geom → {export, render}`.

**Contrat `_glb_to_mesh(path) -> Mesh`** (le seul point non-trivial de `io.py`) :

```python
def _glb_to_mesh(path: Path) -> Mesh:
    """Load a .glb via trimesh and convert to palubicki.Mesh.

    - trimesh.load() returns a Scene; iterate scene.geometry, applying each node's
      world transform to positions and normals.
    - Build one Primitive per source mesh, with a minimal Material:
        base_color = visual.material.baseColorFactor (default (0.7, 0.7, 0.7, 1.0))
        base_color_texture_png = None    # diagnostic mode ignores textures
        alpha_mode = "OPAQUE"            # leaf MASK rebuilt from `--no-leaves` heuristic below
        metallic, roughness = 0.0, 1.0   # ignored by shader, kept for type-compat
        double_sided = visual.material.doubleSided
    - For forests (multi-node Scene), concatenate all primitives into one Mesh.
    - `--no-leaves` heuristic: drop primitives whose base_color is dominantly green
      (g > r and g > b and g > 0.3). Robust without needing alpha_mode preserved.
    """
```

Le heuristique `--no-leaves` repose sur la couleur dominante plutôt que sur `alpha_mode` parce que la roundtrip glTF perd cette flag par défaut côté trimesh. Couleur dominante est suffisamment fiable pour les presets V4 (feuilles vert, écorce brun/gris).

### API publique

```python
from palubicki.render import render_mesh, render_glb, save_png, Camera, RenderError

def render_mesh(
    mesh: Mesh,
    *,
    size: tuple[int, int] = (800, 800),
    camera: Camera | None = None,           # default: Camera.fit(mesh)
    bg: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
    light_dir: tuple[float, float, float] = (-0.3, -1.0, -0.5),
    drop_leaves: bool = False,
) -> np.ndarray: ...                        # (H, W, 4) uint8 RGBA

def render_glb(glb_path: Path, **kwargs) -> np.ndarray: ...

def save_png(image: np.ndarray, path: Path) -> None: ...
```

### Camera

```python
@dataclass(frozen=True)
class Camera:
    elevation_deg: float = 20.0   # 0 = horizon, 90 = top-down
    azimuth_deg: float = 35.0     # rotation around vertical (Y) axis
    target: tuple[float, float, float] = (0.0, 0.0, 0.0)
    distance: float | None = None  # None → auto-fit from bbox
    margin: float = 0.08           # 8% padding around bbox

    @staticmethod
    def fit(mesh: Mesh, **overrides) -> "Camera":
        """Compute target = bbox center, distance from bbox extent.
        Y-up. Concatenates all primitives' positions to build the bbox."""
```

### Pipeline de rendu

Quatre étapes dans `renderer.py`, ~150 LOC total :

**1. Flatten `Mesh` → arrays plats**

```python
def _flatten(mesh: Mesh) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (tri[T,3,3] float32, face_normal[T,3] float32, face_color[T,3] float32)."""
    tris, norms, cols = [], [], []
    for p in mesh.primitives:
        idx = p.indices.reshape(-1, 3)
        tris.append(p.positions[idx])
        n = p.normals[idx].mean(axis=1)
        n /= np.linalg.norm(n, axis=1, keepdims=True).clip(1e-9)
        norms.append(n)
        rgb = np.asarray(p.material.base_color[:3], dtype=np.float32)
        cols.append(np.broadcast_to(rgb, (idx.shape[0], 3)).copy())
    return np.concatenate(tris), np.concatenate(norms), np.concatenate(cols)
```

**2. Shading Lambert flat avec double-sided implicite**

```python
def _shade(normals, face_colors, light_dir):
    L = np.asarray(light_dir, dtype=np.float32)
    L /= np.linalg.norm(L)
    intensity = np.abs(normals @ -L).clip(0, 1)      # abs() = double-sided
    ambient = 0.25
    factor = ambient + (1 - ambient) * intensity
    return (face_colors * factor[:, None]).clip(0, 1)
```

L'`abs()` traite toutes les faces comme double-sided. Faux pour les tubes (faces internes), mais ces faces ne sont jamais visibles parce que les tubes sont fermés. Ça évite de propager `Material.double_sided` jusqu'au shader. Si un cas réel le justifie un jour, on raffinera par primitive.

**3. matplotlib `Poly3DCollection`**

```python
import matplotlib
matplotlib.use("Agg")   # MUST be set before importing pyplot
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

fig = plt.figure(figsize=(size[0]/dpi, size[1]/dpi), dpi=dpi)
fig.patch.set_facecolor(bg[:3]); fig.patch.set_alpha(bg[3])
ax = fig.add_subplot(111, projection="3d", computed_zorder=False)
ax.set_axis_off()
ax.set_proj_type("persp")
coll = Poly3DCollection(tri, facecolors=shaded, edgecolors="none", linewidth=0)
ax.add_collection3d(coll)
ax.set_box_aspect((1, 1, 1))
_apply_camera(ax, camera, mesh_bbox)
```

**4. Encode → ndarray RGBA**

```python
buf = io.BytesIO()
fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", pad_inches=0,
            facecolor=fig.get_facecolor(), transparent=(bg[3] < 1.0))
plt.close(fig)
img = np.asarray(Image.open(buf).convert("RGBA"))
return img
```

### Points d'attention

- **`matplotlib.use("Agg")` forcé en tête du module** avant tout import de pyplot. Sinon, sur Mac, matplotlib peut piocher `MacOSX` ou `Qt5Agg` selon l'env et ouvrir une fenêtre.
- **`computed_zorder=False`** désactive le tri auto de matplotlib (parfois bogué) au profit du painter's natif de `Poly3DCollection`. À ~10k triangles, des artefacts d'ordre sur certaines feuilles peuvent apparaître. Documenté comme limite acceptée du backend.
- **`bbox_inches="tight"`** peut faire varier la taille pixel finale de quelques pixels. Documenté : la `size` demandée est une cible, pas une garantie pixel-exact. Sans importance ici puisqu'on n'asserte pas sur le PNG.

## Intégration CLI

Nouvelle sous-commande dans `cli.py` :

```bash
palubicki preview tree.glb -o tree.png
palubicki preview tree.glb -o tree.png --size 1200x900 --elevation 15 --azimuth 60
palubicki preview forest.glb -o forest.png --bg transparent
```

| Flag | Type | Défaut | Notes |
|---|---|---|---|
| `glb_path` | positional Path | — | un `.glb` produit par `generate` ou `forest` |
| `-o / --output` | Path | requis | PNG cible |
| `--size` | `WxH` | `800x800` | parsing via `_parse_size("1200x900") → (1200, 900)` |
| `--elevation` | float | 20.0 | degrés, transmis à `Camera` |
| `--azimuth` | float | 35.0 | degrés |
| `--distance` | float | None | None → auto-fit |
| `--bg` | `white\|black\|transparent` | `white` | `white` → `(1,1,1,1)`, `black` → `(0,0,0,1)`, `transparent` → `(1,1,1,0)` (canal alpha à 0, RGB blanc pour l'antialiasing sur les bords) |
| `--no-leaves` | flag | False | filtre les primitives à dominante verte (heuristique défini dans `_glb_to_mesh`) |

Implémentation :

```python
def _cmd_preview(args) -> int:
    try:
        from palubicki.render import render_glb, save_png, Camera
    except ImportError:
        print("preview requires the 'render' extra: pip install -e '.[render]'",
              file=sys.stderr)
        return 2
    cam = Camera(
        elevation_deg=args.elevation,
        azimuth_deg=args.azimuth,
        distance=args.distance,
    )
    img = render_glb(
        args.glb_path,
        size=_parse_size(args.size),
        camera=cam,
        bg=_parse_bg(args.bg),
        drop_leaves=args.no_leaves,
    )
    save_png(img, args.output)
    return 0
```

**Hors-scope CLI v1** : pas de `--rotate-gif`, pas de `--side-by-side`, pas de `--annotate` overlay seed/itérations. Notés pour plus tard.

## Gestion d'erreurs

Hiérarchie d'exceptions en miroir de `export.gltf.ExportError` :

```python
# render/__init__.py
class RenderError(Exception): pass
class RenderDependencyError(RenderError): pass
```

| Cas | Détection | Comportement |
|---|---|---|
| matplotlib absent | `ImportError` à l'import du module | `RenderDependencyError`. CLI : message clair "pip install -e '.[render]'" + exit 2. |
| `.glb` introuvable / invalide | `trimesh.load()` retourne `None` ou lève `ValueError` | `RenderError(f"could not load glTF: {path}")`. CLI : exit 1. |
| Mesh vide (0 triangle) | `sum(len(p.indices) for p in mesh.primitives) == 0` | `RenderError("mesh has no triangles to render")`. |
| Mesh dégénéré (bbox extent < 1e-9) | `np.ptp(positions, axis=0).max() < 1e-9` | `RenderError("mesh bounding box is degenerate")`. |
| Taille image absurde | `size[0] <= 0 or size[1] <= 0 or size[0] * size[1] > 50_000_000` | `ValueError` côté `render_mesh`. Garde-fou contre `--size 99999x99999`. |

**Stderr discipline** : aucune écriture directe à `sys.stderr` dans le module `render/`. La CLI (`_cmd_preview`) est responsable d'imprimer au format `"preview error: …"`, cohérent avec `_cmd_generate` (`"export error: …"`).

## Tests

En miroir du pattern existant (`tests/export/`, `tests/golden/`).

### Unitaire — `tests/render/test_renderer.py` (rapide, jamais `slow`)

- `test_flatten_concatenates_primitives` : Mesh avec 2 primitives → arrays concaténés correctement, normales unitaires, couleurs broadcastées.
- `test_shade_lambert_clamps` : normales face à la lumière → intensité ≈ 1.0 ; à l'opposé → ambient (0.25) ; perpendiculaires → ambient.
- `test_camera_fit_centers_target` : Mesh dont la bbox est `[-1, 2]³` → `Camera.fit().target ≈ (0.5, 0.5, 0.5)`.
- `test_render_mesh_returns_rgba_array` : tiny mesh → ndarray `(H, W, 4)` dtype uint8, taille proche du `size` demandé (±50 px à cause de `bbox_inches="tight"`).
- `test_render_empty_mesh_raises` : `Mesh(primitives=[])` → `RenderError`.
- `test_render_degenerate_bbox_raises` : tous points à (0,0,0) → `RenderError`.

### Intégration — `tests/render/test_render_integration.py` (marqué `slow`)

- `test_render_v1_ellipsoid` : `_cfg_ellipsoid` du golden V1 → simulate → build_mesh → render_mesh. Vérifie PNG > 5 KB et > 0.5 % de pixels "non-fond" (un pixel est considéré non-fond si `abs(rgb - bg[:3]*255).max() > 8`, soit ~3 % de drift sur un canal — tolère l'antialiasing sans laisser passer une image vide).
- `test_render_glb_roundtrip` : `generate` un .glb puis `render_glb()` → ndarray valide. Couvre le chargement trimesh + flattening Scene→Mesh.
- `test_render_forest` : fixture forest V3 → ndarray valide. Couvre le path multi-node de trimesh.Scene.

### CLI — extension de `tests/test_cli.py`

- `test_preview_smoke` : génère un .glb, lance `palubicki preview <glb> -o <png>`, assert PNG existe + non vide.
- `test_preview_without_render_extra` : mock ImportError → exit 2, stderr contient `"render extra"`.
- `test_preview_invalid_glb` : chemin bidon → exit 1, stderr contient `"could not load"`.

### Goldens

Aucun PNG n'est asserted. Les goldens SHA-256 buffer restent inchangés et autoritatifs.

**Bonus opt-in** : dans `tests/golden/conftest.py`, ajout d'un flag `--render-on-fail`. Si un golden buffer casse et que le flag est actif, le test génère le PNG du résultat actuel dans `tmp_path/diff/<test>.png` et imprime le path dans le message d'assert. Le PNG de référence n'est pas piné tout de suite — la première fois qu'un golden casse, on régénère et on commit le PNG comme "image de référence" à côté du `.sha256`. Migration progressive, pas de big-bang.

### Couverture

Pas d'objectif chiffré. Le pipeline matplotlib lui-même n'est pas testé en isolation (on fait confiance à matplotlib). Seules les fonctions pures (`_flatten`, `_shade`, `Camera.fit`) doivent avoir une coverage de 100 %.

## Hors-scope

- **Textures** (bark, leaf alpha-mask) : niveau diagnostic ne les couvre pas. Reste possible plus tard si on swap le backend.
- **Ombres** : impossible avec matplotlib `Poly3DCollection`, demanderait un vrai moteur de rendu.
- **GIF rotatif / animation** : reporté.
- **Side-by-side de deux arbres** : reporté ; usage notebook permet déjà de composer deux ndarray.
- **Annotations overlay** (seed, n_iterations) : reporté ; usage notebook permet déjà via matplotlib.
- **Render direct depuis un `Tree` (sim output, pas Mesh)** : passe par `build_mesh` puis `render_mesh`. Pas de raccourci API.
- **Comparaison PSNR/SSIM** : décidée out (Q3). On reste sur SHA buffer.

## Plan de livraison

Une seule PR, ordonnée :

1. `pyproject.toml` : ajouter extra `render = ["matplotlib>=3.7"]` (Pillow est déjà core).
2. `src/palubicki/render/{__init__.py, camera.py, renderer.py, io.py}` avec exceptions + API publique.
3. Tests unitaires `tests/render/test_renderer.py`.
4. Sous-commande `preview` dans `cli.py` + tests CLI.
5. Tests d'intégration `tests/render/test_render_integration.py` (marqués `slow`).
6. `tests/golden/conftest.py` : flag `--render-on-fail` opt-in.
7. README : section "Preview" sous "Usage" avec les trois cas (CLI, notebook, golden artefact).
