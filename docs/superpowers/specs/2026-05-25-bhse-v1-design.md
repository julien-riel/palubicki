# Palubicki V1 — Générateur d'arbres 3D BHse → glTF

**Date** : 2026-05-25
**Statut** : Design validé, prêt pour implémentation
**Référence** : Palubicki, Horel, Longay, Runions, Lane, Měch, Prusinkiewicz. *Self-organizing tree models for image synthesis*. SIGGRAPH 2009.

## Contexte & objectif

Construire un générateur d'arbres 3D en ligne de commande, écrit en Python, qui produit des fichiers glTF binaires (`.glb`) à partir d'une simulation procédurale fidèle au modèle **BHse** (Borchert-Honda + Self-organization avec compétition d'espace) du papier de Palubicki et al.

Ce document couvre **uniquement la V1**. La roadmap (V2 ombrage lumineux voxelisé, V3 obstacles + inter-arbres, V4 presets d'espèces) est documentée séparément dans `docs/superpowers/roadmap/` ; chaque jalon aura son propre spec et plan d'implémentation.

## Scope V1

**Inclus** :
- Modèle BHse complet : marker points dans une enveloppe paramétrique, perception par cône, compétition closest-bud, allocation Borchert-Honda (basipète + acropète), tropismes (gravitropisme, phototropisme global directionnel, inertie), shedding sur fenêtre glissante.
- Enveloppes : sphère, ellipsoïde, cône, demi-ellipsoïde.
- Géométrie : tubes continus tessellés sur chaînes d'axes (parallel transport frames), rayons par pipe model, feuilles cross-quad sur bourgeons terminaux.
- Export `.glb` core glTF 2.0 (aucune extension), matériaux PBR bark + leaf alpha-masked, texture leaf par défaut générée à la volée.
- CLI argparse avec deux sous-commandes (`generate`, `dump-defaults`, plus `dump-config` pour extraire la config embarquée d'un `.glb`), configuration YAML, déterminisme par seed.

**Exclus** (jalons ultérieurs) :
- Ombrage lumineux voxelisé (BHls) → V2.
- Obstacles, interaction inter-arbres, plagiotropisme avancé → V3.
- Presets d'espèces reproduisant la Figure 12 du papier → V4.
- Animations, skinning, LOD, textures bark, subdivision surface, fusion de jonctions par déformation locale.

## Stack technique

- Python 3.11+
- `numpy` — buffers et math vectorisée
- `scipy.spatial.cKDTree` — recherche de voisinage marker↔bud
- `pygltflib` — sérialisation glTF/GLB
- `Pillow` — génération texture leaf par défaut
- `pyyaml` — chargement config
- `pytest` + `pytest-cov` — tests
- Empaquetage `pyproject.toml` (PEP 621), buildable via `uv` ou `pip`

Pas de framework lourd type `trimesh` : on gère nos buffers numpy directement.

## Architecture

Couches avec frontières explicites. Chaque couche ne dépend que des couches inférieures.

```
cli/  ──► sim/  +  geom/  ──► export/
                    │            │
                    └─► Mesh ────┘   (format neutre)
```

- `sim/` ignore tout des triangles et du glTF.
- `geom/` reçoit un `Tree` + `Config`, produit un `Mesh` neutre.
- `export/` reçoit un `Mesh`, produit un `.glb`. Réutilisable si on ajoute USD/OBJ.
- `cli/` orchestre.

### Arborescence

```
palubicki/
├── pyproject.toml
├── README.md
├── src/palubicki/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── sim/
│   │   ├── envelope.py          # MarkerSource: Sphere, Ellipsoid, Cone, HalfEllipsoid
│   │   ├── markers.py           # MarkerCloud (positions, alive mask, KDTree)
│   │   ├── tree.py              # Tree, Bud, Node, Internode
│   │   ├── space_competition.py # perception cone, closest-bud, direction perçue
│   │   ├── bh.py                # allocation BH (basipète, acropète)
│   │   ├── tropisms.py          # composition gravité + phototropisme + inertie
│   │   ├── shedding.py          # historique Q + critère de chute
│   │   └── simulator.py         # boucle iter: perceive → allocate → grow → shed
│   ├── geom/
│   │   ├── radii.py             # pipe model
│   │   ├── tubes.py             # squelette → tubes tessellés
│   │   ├── leaves.py            # cross-quads sur bourgeons terminaux
│   │   └── mesh.py              # dataclass Mesh, Primitive, Material
│   └── export/
│       └── gltf.py              # Mesh → .glb
└── tests/
    ├── sim/  geom/  export/  integration/  golden/
    └── conftest.py
```

## Modèle de simulation

### Entités

```python
@dataclass
class Bud:
    position: np.ndarray            # (3,)
    direction: np.ndarray           # (3,) unit
    axis_order: int                 # 0 = main, 1+ = lateral
    parent_node: "Node"
    age: int = 0
    state: BudState                 # ACTIVE | DORMANT | DEAD

@dataclass
class Internode:
    parent_node: "Node"
    child_node: "Node"
    length: float
    diameter: float = 0.0           # rempli en post-sim par pipe model
    quality_history: deque[float]   # pour le shedding
    is_main_axis: bool

@dataclass
class Node:
    position: np.ndarray
    parent_internode: "Internode | None"
    children_internodes: list["Internode"]
    terminal_bud: "Bud | None"      # bourgeon apical
    lateral_buds: list["Bud"]

class Tree:
    root: Node
    active_buds: list[Bud]
    all_internodes: list[Internode]
```

`MarkerCloud` détient `positions: (N,3)`, `alive: (N,) bool`, et un `scipy.spatial.cKDTree` reconstruit après chaque pruning.

### Boucle d'un pas

À chaque itération `t` :

1. **Perception** (`space_competition.perceive`) — pour chaque bud actif :
   - Query KDTree des markers vivants dans une boule de rayon `r_perception`.
   - Filtre par cône : `cos(angle(m - p_b, d_b)) ≥ cos(θ_perception)`.
   - Compétition closest-bud : chaque marker est attribué au bourgeon le plus proche parmi ceux qui le perçoivent.
   - Sortie par bud : `Q(b) = nombre de markers attribués`, `v_perc(b) = normalize(Σ normalize(m_i − p_b))`.

2. **Allocation BH** (`bh.allocate`) — deux passes :
   - **Basipète** (post-order) : `v(internode) = Σ v(child) + Q(bud)` pour les buds du nœud enfant.
   - `v_total = α · v(root)`.
   - **Acropète** (pre-order) : à chaque embranchement,
     `v_main = v · λ·Q_m / (λ·Q_m + (1−λ)·Q_l)`, `v_lat = v − v_main`.
   - Chaque bud reçoit `n_b = floor(v_b)` (pas de carry-over en V1).

3. **Croissance** — pour chaque bud avec `n_b ≥ 1`, répéter `n_b` fois :
   - `d_new = normalize(w_perc · v_perc + w_grav · g + w_phot · p_global + w_dir · d_b)`.
   - Si aucun marker perçu → bud reste DORMANT pour ce step (pas de croissance à l'aveugle).
   - Créer un internode de longueur `L`, un nœud enfant.
   - Insérer 1 bud terminal continuant l'axe et K bourgeons latéraux selon phyllotaxie (`ALTERNATE` avec angle de divergence 137.5° par défaut, `OPPOSITE`, `WHORLED(k)`).
   - Marquer le bud parent DEAD.

4. **Pruning markers** — supprimer tous markers à distance `< r_kill` des nouveaux nœuds. Rebuild KDTree.

5. **Shedding** — chaque internode push sa `Q` dans `quality_history` (fenêtre `W`). Si la moyenne sur W reste `< threshold_shed`, retirer la sous-arborescence.

6. **Arrêt** : `t ≥ max_iterations` OU aucun bud actif OU aucun nouveau nœud créé pendant 2 steps consécutifs.

### Tropismes

Trois composantes additives normalisées :
- **Gravitropisme** : `(0, ±1, 0)` (positif = vers le haut).
- **Phototropisme global directionnel** : vecteur unitaire fixé par config (pas de gradient 3D en V1 — réservé V2 avec BHls).
- **Inertie directionnelle** : `d_b` courant, atténue les virages.

Garde sur `v_perc = 0` si aucun marker perçu.

### Déterminisme

Toute la stochasticité (sampling markers, jitter éventuel) passe par un unique `numpy.random.Generator(seed)` construit dans `Config`. Aucune autre source de hasard.

### Complexité visée

~50k markers, ~5k internodes, ~30 itérations → quelques secondes. KDTree query O(log N) par bud. Pas d'optimisation prématurée.

## Géométrie

### Pipe model

Module `geom/radii.py`. Post-order :
- Internode terminal : `r = r_tip` (défaut 0.005 m).
- Internode interne : `r = (Σ r_child^n)^(1/n)`, `n=2.49` par défaut.

### Chaînes d'axes

Module `geom/tubes.py`. On ne tube **pas** par internode (joints visibles). On regroupe en chaînes :
- Démarre à la racine ou à un embranchement latéral.
- Continue par l'internode `is_main_axis=True` à chaque embranchement.
- Se termine au prochain feuille ou à la fin de l'axe.

### Tessellation

Pour chaque chaîne :

1. **Frame initial** : `t₀ = direction sortante`. `right₀` = premier axe canonique non colinéaire à `t₀`, projeté par Gram-Schmidt. `up₀ = t₀ × right₀`.
2. **Parallel transport** node à node : rotation minimale envoyant `t_{i-1}` sur `t_i` (Rodrigues), appliquée à `right` et `up`. Évite le twist.
3. **Ring** à chaque nœud : N sommets (défaut 8) sur le cercle de rayon `r_i = (r_in + r_out)/2`.
4. **Normales** : radiales (lissage gratuit).
5. **UV** : `u = k/N` (loop avec colonne dupliquée à u=1), `v = longueur cumulée / v_scale`.
6. **Indices** : quads triangulés entre rings consécutifs.
7. **Cap racine** : fan triangulaire fermant le tronc à `y=0`. Pas de cap aux tips.

### Jonctions

Approche V1 — **insertion simple** : tube latéral démarre à la position du nœud, sans booléen ni merge. Coutures visibles à très courte distance, acceptable. Amélioration V2 : "branch socket" par déformation locale du ring parent.

### Feuilles

Pour chaque bud terminal survivant (ACTIVE ou DORMANT) :
- **Cross-quad** : deux quads perpendiculaires `leaf_size × leaf_size`, tournés autour de `bud.direction`, centrés sur `bud.position + bud.direction · offset_petiole`.
- 8 vertices, 12 indices par feuille.
- UVs 0..1 sur chaque quad.

### Matériaux

- **Bark** : PBR `baseColorFactor=[0.35, 0.22, 0.12, 1.0]`, `metallic=0`, `roughness=0.9`. Pas de texture en V1.
- **Leaf** : PBR + `baseColorTexture`, `alphaMode=MASK`, `alphaCutoff=0.5`, `doubleSided=true`. Texture par défaut Pillow-générée si non fournie, embarquée dans le chunk binaire du `.glb` via bufferView (cf. §Export).

### Mesh neutre

```python
@dataclass
class Material:
    name: str
    base_color: tuple[float, float, float, float]
    metallic: float
    roughness: float
    base_color_texture_png: bytes | None
    alpha_mode: str          # "OPAQUE" | "MASK"
    alpha_cutoff: float
    double_sided: bool

@dataclass
class Primitive:
    positions: np.ndarray    # (V, 3) float32
    normals: np.ndarray      # (V, 3) float32
    uvs: np.ndarray          # (V, 2) float32
    indices: np.ndarray      # (M,)   uint32
    material: Material

@dataclass
class Mesh:
    primitives: list[Primitive]   # V1: [bark, leaves]
```

### Coût attendu

5k internodes × 2k chaînes courtes × 8 sides → ~40k vertices bark + ~8k vertices feuilles = ~50k vertices, ~100k triangles.

## Export glTF

Module `export/gltf.py`. Fonction publique unique :
```python
def write_glb(mesh: Mesh, output_path: Path, *, asset_meta: dict) -> None
```

### Mapping

Une seule mesh glTF avec deux primitives, attachée à un nœud racine `tree_root`. Une scène.

```
asset (generator: "palubicki vX.Y.Z", version: "2.0")
scenes[0].nodes -> [0]
nodes[0]        -> { name: "tree_root", mesh: 0 }
meshes[0]       -> { primitives: [bark_prim, leaves_prim] }
materials[0]    -> bark
materials[1]    -> leaf (alphaMode MASK, doubleSided, baseColorTexture)
textures[0]     -> { source: images[0], sampler: samplers[0] }
images[0]       -> PNG embarquée (BIN chunk)
samplers[0]     -> { magFilter: LINEAR, minFilter: LINEAR_MIPMAP_LINEAR, wrapS/T: REPEAT }
```

### Buffer packing

`.glb` mono-fichier. Concaténation respectant l'alignement 4-byte. Accessors :
- POSITION : `FLOAT VEC3`, `min`/`max` calculés (requis spec).
- NORMAL : `FLOAT VEC3`.
- TEXCOORD_0 : `FLOAT VEC2`.
- INDICES : `UNSIGNED_INT SCALAR`.

Construction explicite de l'objet `GLTF2` (pas de helpers high-level pygltflib) pour contrôler accessors/bufferViews.

### Métadonnées

- `asset.generator` = `f"palubicki {__version__}"`.
- `asset.copyright` propageable.
- `asset.extras` : `{"seed": ..., "config": <YAML effectif>, "iterations": ..., "envelope": ...}` — reproductibilité.

### Cas limites

- Mesh vide → `ExportError("empty mesh — simulation produced no geometry")`.
- IOError → laisser remonter au CLI (exit 1, message clair).

### Validation

Option `--validate` : rouvre le `.glb` avec `pygltflib`, vérifie round-trip counts. Pas de dépendance `gltf-validator` externe en V1.

### Hors scope export

- Pas d'animations, skinning, morph targets, LOD.
- Pas d'extensions glTF (strict core 2.0 → compatibilité maximale).

## CLI & configuration

### Sous-commandes

```
palubicki generate [OPTIONS] -o OUTPUT.glb
palubicki dump-defaults [--envelope ellipsoid] > config.yaml
palubicki dump-config tree.glb > used_config.yaml
```

### Précédence

`defaults < YAML (--config) < CLI flags`. Fusion via `Config.from_sources(yaml_path, cli_args)`. `Config` est `frozen=True`.

### Config dataclasses

```python
@dataclass(frozen=True)
class EnvelopeConfig:
    shape: Literal["sphere", "ellipsoid", "cone", "half_ellipsoid"]
    rx: float; ry: float; rz: float
    center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    marker_count: int = 20_000

@dataclass(frozen=True)
class SimConfig:
    r_perception: float = 0.6
    theta_perception_deg: float = 90.0
    r_kill: float = 0.15
    internode_length: float = 0.1
    alpha_basipetal: float = 2.0
    lambda_apical: float = 0.55
    max_iterations: int = 30

@dataclass(frozen=True)
class TropismConfig:
    w_perception: float = 1.0
    w_gravity: float = 0.3
    w_phototropism: float = 0.0
    w_direction_inertia: float = 0.4
    photo_direction: tuple[float, float, float] = (0.0, 1.0, 0.0)

@dataclass(frozen=True)
class PhyllotaxyConfig:
    mode: Literal["alternate", "opposite", "whorled"] = "alternate"
    whorl_count: int = 3
    divergence_angle_deg: float = 137.5
    branch_angle_deg: float = 45.0

@dataclass(frozen=True)
class SheddingConfig:
    quality_threshold: float = 0.0
    window: int = 5
    enabled: bool = True

@dataclass(frozen=True)
class GeomConfig:
    ring_sides: int = 8
    r_tip: float = 0.005
    pipe_exponent: float = 2.49
    leaf_size: float = 0.06
    leaf_texture: Path | None = None
    bark_color: tuple[float, float, float] = (0.35, 0.22, 0.12)

@dataclass(frozen=True)
class Config:
    envelope: EnvelopeConfig
    sim: SimConfig
    tropism: TropismConfig
    phyllotaxy: PhyllotaxyConfig
    shedding: SheddingConfig
    geom: GeomConfig
    seed: int = 0
    output: Path = Path("tree.glb")
    log_level: str = "INFO"
```

### Flags CLI principaux

Sélection des paramètres les plus tweakés (reste via YAML) :

```
--config PATH
--seed INT
--envelope {sphere,ellipsoid,cone,half_ellipsoid}
--envelope-radii Rx Ry Rz
--marker-count INT
--iterations INT
--lambda FLOAT
--w-gravity FLOAT
--leaf-texture PATH
--no-leaves
--no-shed
--ring-sides INT
--log-level {DEBUG,INFO,WARN,ERROR}
--validate
--save-config PATH
-o, --output PATH
```

Argparse (pas de Click — limiter les deps).

### Validation

`Config.__post_init__` :
- Rayons > 0, `marker_count > 0`, `theta_perception_deg ∈ (0, 180]`.
- `lambda_apical ∈ [0, 1]`, `pipe_exponent ∈ [1, 4]`.
- `ring_sides ≥ 3`.
- Parent de `output` existe.

`ConfigError` → exit 2 (distinct de runtime exit 1).

### Logging

`logging` standard. Format :
```
[12.3s] sim/iter 14/30  buds=482 active=312  internodes=2841  shed=12
```

Progress en INFO par itération. DEBUG pour markers/Q distribution. Pas de progress bar rich.

### Exemples

```bash
palubicki generate -o oak.glb \
  --envelope half_ellipsoid --envelope-radii 4 6 4 \
  --seed 42

palubicki generate -o pine.glb \
  --envelope cone --envelope-radii 2 8 2 \
  --w-gravity 0.5 \
  --config configs/conifer.yaml
```

### Reproductibilité

Config effective embarquée dans `asset.extras.config` du `.glb`. Extraction via `palubicki dump-config tree.glb`.

## Stratégie de tests

`pytest` + `numpy.testing`. Structure miroir de `src/`. Pas de mocking — injection par constructeur.

### Niveaux

**Unitaires** (<100 ms chacun) :
- `tests/sim/test_envelope.py` : rejection sampling correct, distribution uniforme (chi-carré), déterminisme.
- `tests/sim/test_space_competition.py` : cône de perception, closest-bud unique, direction perçue symétrique.
- `tests/sim/test_bh.py` : cas trivial (1 bud), embranchement analytique, conservation `v_main + v_lat = v_node`.
- `tests/sim/test_tropisms.py` : `w_gravity=1` seul → `+Y`, tous poids 0 → `d_b` conservé.
- `tests/sim/test_shedding.py` : historique vide → shed, sous-arborescence DEAD propre.
- `tests/geom/test_radii.py` : tip seul → `r_tip`, 2 tips → `r_tip · 2^(1/n)`.
- `tests/geom/test_tubes.py` : chaîne droite (counts, normales radiales), chaîne courbée (pas de twist), pas de NaN.
- `tests/geom/test_leaves.py` : 1 bourgeon → 8 vertices, 12 indices, normales perpendiculaires.

**Intégration** (sec/min) :
- `tests/integration/test_smoke_generate.py` : configs minuscules (`marker_count=200`, `max_iterations=5`), 3-4 enveloppes, round-trip vérifié.
- `tests/integration/test_cli.py` : `subprocess.run`, exit codes (0 success, 2 config invalide).

**Golden** :
- `tests/golden/` : 2-3 `.glb` de référence (seeds + configs fixés).
- Comparaison hash SHA256 des buffers binaires (positions, normales, indices).
- Diff résumé en cas d'échec. Régénération manuelle via `pytest --update-goldens` après revue visuelle, commit séparé.

### Marqueurs

- `pytest -m "not slow"` par défaut, suite unitaire < 5 s.
- `pytest -m "slow"` pour intégration + golden.
- CI lance les deux.

### Fixtures (`tests/conftest.py`)

- `rng(seed=42)` → `numpy.random.Generator`.
- `tiny_config()` → `Config` minuscule.
- `linear_tree(n=5)` → `Tree` mock à la main.

### Couverture

`pytest-cov` ; cible 80% sur `sim/` et `geom/`, 60% global. Métrique de progression, pas gate stricte.

### TDD

Plan d'implémentation suivant la skill `superpowers:test-driven-development` : test → impl par sous-module. Les tests unitaires sont la spec exécutable.

### Hors scope tests V1

- Tests visuels automatisés (pyrender + diff PNG).
- Tests de perf budgétés.
- Fuzzing inputs.

## Risques et limitations connues

1. **Jonctions tubes simplistes** : insertion sans booléen, coutures visibles à courte distance. Documenté ; amélioration V2.
2. **Pas de carry-over fractionnaire BH** : `floor(v_b)` jette les restes ; peut produire des arbres légèrement moins denses qu'avec accumulation. Toggleable en V2 si visiblement problématique.
3. **Phototropisme V1 = direction globale fixe** : pas de gradient 3D ni d'auto-occlusion. C'est par design ; BHls (V2) résout.
4. **Performance pur-Python** : OK pour ~5k internodes, dégradation visible >20k. Optimisation différée à un baseline mesuré.
5. **Reproductibilité cross-platform** : sortie déterministe garantie sur même version Python + numpy + scipy. Changement de version mineure de scipy peut altérer KDTree → goldens à régénérer.

## Roadmap (référence)

- **V2 BHls** : grille de voxels d'ombrage propagée depuis les feuilles, perception de lumière par bourgeon, intégration dans le critère de croissance et de shedding.
- **V3 obstacles + inter-arbres** : modélisation de boîtes/meshes occluant la croissance, partage de marker cloud entre plusieurs arbres simulés conjointement.
- **V4 species presets** : configs YAML reproduisant les espèces de la Figure 12 du papier (pommier, chêne, etc.), texture bark, leaf textures spécifiques.

Chaque jalon = son propre spec dans `docs/superpowers/specs/` + son plan d'implémentation.
