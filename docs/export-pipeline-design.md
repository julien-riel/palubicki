# Pipeline d'export : du graphe FSPM aux assets `.glb` — conception & plan

*Conception de la **fabrique d'assets** de palubicki : comment transformer le
résultat d'une simulation (le graphe d'arbres de [`sim/tree.py`](../src/palubicki/sim/tree.py))
en fichiers `.glb` exploitables à la fois pour le **photoréalisme** (archviz,
Blender/Cycles, Unreal Lumen) et pour une **forêt de jeu vidéo** (instancing,
LOD, impostors), avec **animation/squelette de vent** pour l'interaction.*

> **Relation aux autres docs.** Ce document est la **conception + le plan** ;
> [`render-pipeline.md`](./render-pipeline.md) est la **référence** (le quoi/pourquoi
> technique) et l'épic [#53](https://github.com/julien-riel/palubicki/issues/53)
> en est le suivi. Ce document **corrige** plusieurs hypothèses de la référence à
> la lumière d'une recherche 2026 sur l'état réel des moteurs (voir §3) et
> propose un **ordre d'implémentation différent** (la forêt d'abord, pas le
> look) avec un argumentaire chiffré.
>
> **Méthode.** Les suggestions ci-dessous ont d'abord été produites de façon
> *indépendante* (recherche fraîche multi-angles + cartographie du code), puis
> réconciliées avec l'existant — pour éviter l'ancrage sur la première
> réflexion. Tous les faits-code porteurs sont cités `fichier:ligne` et ont été
> vérifiés directement.

---

## 1. Le problème en une phrase

Le graphe FSPM est *correct* mais ce n'est pas un *asset* : pas de triangles, de
UV, de matériaux, de LOD, de pivot, de rig de vent. Le pipeline d'export est la
projection (avec perte, et pleine d'arbitrages budget-vs-fidélité) de l'état
biologiquement fidèle vers « quelque chose qu'un GPU dessine 60 fois par
seconde ». Trois cibles très différentes (hero photoréaliste, arbre de jeu
moyen, forêt lointaine) sortent du **même** graphe.

---

## 2. North star : UN master canonique + des profils cibles

> palubicki émet **un** `.glb` master canonique par arbre — PBR
> metallic-roughness standard, **non compressé**, textures PNG — comme **source
> de vérité unique**, puis dérive un petit nombre de **profils cibles** par des
> passes finales de post-traitement.

Conséquences directes :

- **Le graphe `sim/` reste en lecture seule.** Le travail de l'export est de
  *lever* la structure latente du graphe vers des attributs portables, **jamais**
  de baker des préoccupations de rendu dans les structures de simulation :
  - `Internode.diameter` → raideur de vent (stiffness)
  - `Bud.axis_order` (via `diagnostics._axis_orders`) → niveaux de vent + élagage LOD
  - `Bud.axis_node_ordinal` → phase de vent **stable** (jamais `node_index` global)
  - `Internode.light_factor` → soleil/ombre
  - `Internode.birth_time` → âge d'écorce (gradient de teinte)
- **La réalité moteur, pas l'élégance de la spec, est la contrainte liante.**
  L'importeur glTF d'Unreal (GLTFCore/Interchange) ne lit **ni** Draco, **ni**
  meshopt, **ni** KTX2, **ni** `EXT_mesh_gpu_instancing`, **ni** les extensions de
  matériau (transmission/volume/specular/sheen). Cela fixe le **plancher** : le
  master doit fonctionner *sans* tout ça. Un profil non compressé/PNG est donc
  **obligatoire**, pas optionnel.
- **Les looks-signature qu'aucune extension portable ne sait porter
  aujourd'hui** (translucence des feuilles à contre-jour, mouvement hiérarchique
  de vent) sont délibérément livrés par des **shaders par-moteur** alimentés par
  un **contrat d'attributs portable** ; les extensions glTF correspondantes ne
  sont émises que comme **métadonnées prospectives**, documentées comme
  *ignorées par les moteurs aujourd'hui*.
- **Le réalisme mène** (lames de feuilles géométriques, PBR normal+ORM complet,
  gestion correcte des espaces colorimétriques) parce qu'on est en mode PoC sans
  contrainte de rétro-compatibilité ; l'**optimisation** (compression,
  instancing, impostors) se greffe à la fin, et un fallback non compressé est
  toujours conservé.

---

## 3. Ce que la recherche fraîche **corrige** dans l'existant

C'est le cœur de l'enrichissement. `render-pipeline.md` (§12) et #53 sont justes
sur l'inventaire des lacunes ; la recherche 2026 sur l'état réel des quatre
moteurs cibles (three.js, Blender 4.x, Unreal GLTFCore/Interchange, Unity
glTFast) les **corrige** sur plusieurs points de priorisation et de faisabilité :

| Sujet | Hypothèse existante | Correction 2026 | Impact sur la conception |
|---|---|---|---|
| **Translucence des feuilles** | `KHR_materials_diffuse_transmission` comme défaut, avec fallback | L'extension est en **Release Candidate non ratifiée** et **non supportée** par three.js, Blender, Unreal **ni** Unity. La construire en défaut = feuilles **plates et opaques partout**. `KHR_materials_transmission` est une mauvaise physique (verre spéculaire, écran-espace, artefacts sur feuilles qui se chevauchent). | Le défaut devient un **masque thickness/translucence** (lame claire, nervures/pétiole sombres) en alpha de texture + poids par-sommet, consommé par des shaders **subsurface par-moteur** (Unreal *Two-Sided Foliage*, Unity HDRP *Translucent*). `diffuse_transmission` émis seulement en métadonnée prospective. |
| **LOD** | `MSFT_lod` comme mécanisme | `MSFT_lod` est une **extension vendor MSFT morte** : ignorée par three.js, Blender, Unreal **et** Unity. | LOD discret en **4 paliers** ; `MSFT_lod` + `MSFT_screencoverage` seulement pour les **viewers web** ; les moteurs utilisent leurs **LOD groups natifs** ; on **laisse le master pleine densité** pour que Nanite (Unreal) pilote son propre auto-LOD. L'impostor est le dernier palier universel. |
| **Attributs de vent** | « `COLOR_0` ou un attribut custom » | Les attributs **`_underscore` custom sont silencieusement abandonnés** par three.js et Unity glTFast à l'import (et la spec interdit l'uint dessus). | Encoder **uniquement** dans `COLOR_n`/`TEXCOORD_n` (float). `COLOR_0` = `(phase, stiffness, leafMask)`, `TEXCOORD_1` = pivot de branche. Et : Unity ne conserve l'attribut **que si le matériau le déclare**. |
| **TANGENT** | Implicite (« normal maps ») | Sans **TANGENT explicite**, les îlots UV miroités produisent des coutures et un éclairage faux. Aujourd'hui **non exporté** (`Primitive` n'a pas de champ `tangents`, [`mesh.py:22-29`](../src/palubicki/geom/mesh.py)). | Émettre `TANGENT` (VEC4, handedness MikkTSpace). **Quasi-gratuit** pour les tubes : le repère parallel-transport est déjà calculé puis jeté ([`tubes.py:249-259`](../src/palubicki/geom/tubes.py)). C'est un **prérequis** des normal maps → met le vent (qui émet TANGENT) avant les matériaux. |
| **Forêt** | Émettre arbre-à-l'origine + transforms de node (correct) | `write_glb_forest` **bake les sommets en coordonnées-monde** par arbre, `node.translation` **inutilisé** ([`gltf.py:163-264`](../src/palubicki/export/gltf.py)), arbres enracinés à `envelope.center`. + subtilité ignorée : **chaque arbre a une topologie unique** (RNG seed distinct, [`forest.py`](../src/palubicki/sim/forest.py)). | Émettre **arbre-unité à son origine locale** + `EXT_mesh_gpu_instancing` (T/R/S). Granularité : **partager le mesh quand les configs coïncident**, sinon **instance-of-one** (un node de count 1 portant juste son transform-monde). Le gain (zéro sommet-monde baké, placement par transform) tient dans les deux cas. |
| **Impostor / rasterizer** | « impostor octaédral depuis `render/renderer.py` » | `render/renderer.py` est **matplotlib (écran-espace)** : **incapable** de rendre hors-écran multi-angles. | Impostor **hémi-octaédral** (12×12–16×16, BaseColor+Normal+Depth) ; nécessite un **backend GL headless** (moderngl/pyrender) qui remplace matplotlib — c'est le **plus gros risque d'infra**, isolé derrière `export/impostor.py`. |
| **Vent : skin vs attributs** | Les deux présentés à égalité | Le skin (skin+joints glTF) coûte *bones × instances* et **force un draw call par arbre** : prohibitif à l'échelle forêt. | **Attributs-sommets = défaut et seule voie forêt** ; skin glTF réservé à **un seul hero tree** au premier plan (lecture sans shader custom). |
| **Autorité sur « supporté »** | Tables de support statiques | Les tables **dérivent à chaque release** (numéros three.js, points Blender 4.x, Unity glTFast 6.x, migration Unreal 5.4→5.7 Interchange). | Une extension n'est documentée « supportée » qu'après passage d'un **gate Validator Khronos + round-trip 4 moteurs**, rejoué par version. |

---

## 4. Architecture en couches

```text
L0  SIM (lecture seule)        sim/tree.py, simulator.py, forest.py, radii.py,
    graphe figé                diagnostics.py, light.py, sag.py, caducity.py
        │  (jamais muté par l'export)
        ▼
L1  AUTHORING / RIG-PARAM      NOUVEAU geom/wind.py
    dérivation des scalaires   phase = hash(axis_node_ordinal le long de l'axe)
    de look/vent par 1 passe   stiffness = clamp((diameter - d_min)/(d_max - d_min))
    en lecture seule           wind_tier = min(2, axis_order)
                               branch_pivot = parent.position + sag_offset
        │                       (+ arbre de joints + IBM pour la voie skin opt.)
        ▼
L2  GÉOMÉTRIE + ATTRIBUTS      ÉTEND tubes.py / leaves.py / mesh.py
    + BAKE MATÉRIAUX           NOUVEAU geom/leaf_blade3d.py (lame courbée 3D),
    estampille L1 sur sommets  geom/maps.py (normal Sobel, ORM, thickness),
    élargit le modèle de       geom/tangents.py
    données, bake les maps     ÉTEND _textures.py (champ de hauteur + nervures)
        │  COLOR_0=(phase,stiffness,leafMask)  TEXCOORD_1=pivot  TANGENT
        ▼  teinte automne/écorce → COLOR_1
L3  ASSEMBLAGE glTF CANONIQUE  REFACTOR export/gltf.py → package export/gltf/
    le master non compressé    boucle d'accessors data-driven (tous attributs présents)
                               racine du collet à (x,0,z) exact, Y-up, mètres
                               extensionsUsed, provenance dans asset.extras
                               forêt = arbre-unité + EXT_mesh_gpu_instancing
        │                       NOUVEAU export/instancing.py ; skin opt. _skin.py
        ▼
L4  PROFILS CIBLES + POST-BAKE NOUVEAU export/profiles.py, lod.py, impostor.py
    dérivés du master unique   WEB_UNITY  : gltfpack meshopt + quantization + KTX2
                                            + gpu_instancing + extensions complètes + LOD/impostor
                               UNREAL_DCC : non compressé + PNG + instances aplaties/sidecar
                                            + extensions import-safe uniquement
        │  (le master PNG non compressé est TOUJOURS conservé)
        ▼
TRANSVERSE  VALIDATION / VIEWER / CI
    NOUVEAU tests/export/test_gltf_validation.py (Validator Khronos + round-trip trimesh
    + goldens de sémantique d'attributs) ; ÉTEND edit/static (shader de vent de référence)
```

---

## 5. Flux de données end-to-end

1. **Graphe FSPM** — `simulate()`/`simulate_forest()` produisent un `Tree` figé
   (`Node.position`, `Internode.diameter/is_main_axis/light_factor/birth_time/vigor`,
   `Bud.axis_order/axis_node_ordinal`, `Leaf.state/azimuth`, `Node.sag_offset`).
   `diagnostics` reconstruit `axis_order` et l'ordre de Strahler **à la demande**
   depuis la topologie `is_main_axis` (pas de champ stocké — cohérent avec le
   reste du projet).
2. **Dérivation rig-param** (L1, `geom/wind.py`) — une traversée en lecture seule
   calcule phase / stiffness / wind_tier / branch_pivot par internode et feuille.
   Les constantes `d_min`/`d_max` sont lues sur **la plage de diamètres réelle de
   l'arbre** (pas une constante figée) pour que la hiérarchie de mouvement
   survive aux dérives du modèle de pipe (exponent/unités).
3. **Estampille géométrie + attributs** (L2) — `tubes.py` parcourt
   `_collect_chains` (groupe déjà par chaîne `is_main_axis`) et diffuse, par
   anneau, `(phase, stiffness, leafMask=0)` dans `COLOR_0`, le pivot dans
   `TEXCOORD_1`, et émet `TANGENT` depuis les `rights/ups`
   ([`tubes.py:249-259`](../src/palubicki/geom/tubes.py), aujourd'hui jetés).
   `leaves.py`/`leaf_blade3d.py` émettent les lames (`leafMask=1`, phase de l'axe
   parent, stiffness basse, tier 2, TANGENT du repère de lame, poids thickness) ;
   la teinte d'automne passe sur `COLOR_1`.
4. **Matériaux/textures** (L2, `geom/maps.py` + `_textures.py`) — normale d'écorce
   bakée depuis un **champ de hauteur propre** par Sobel (`N=normalize(-dh/du,-dh/dv,1)`,
   OpenGL +Y) ; ORM packé `O→R / Rough→G / Metal→B` (linéaire) ; masque
   thickness/translucence des feuilles en alpha. Gestion couleur imposée :
   baseColor/emissive **sRGB**, ORM/normal **linéaire**.
5. **Assemblage glTF** (L3, `export/gltf/`) — boucle d'accessors data-driven émet
   tout attribut présent ; matériaux câblent baseColor/normal/ORM/occlusion/
   emissive/thickness + extensions import-safe ; arbre unique placé collet à
   `(x,0,z)` Y-up mètres ; forêts = arbre-unité + buffers `EXT_mesh_gpu_instancing`
   T/R/S + `EXT_instance_features` (`_SPECIES,_SEED,_AGE,_PHASE`). **Sortie = le
   master canonique non compressé PNG.**
6. **Variantes `.glb`** (L4, `export/profiles.py`) — du master unique, gltfpack /
   glTF-Transform dérivent WEB_UNITY et UNREAL_DCC. Chaîne LOD (`export/lod.py`)
   et impostor hémi-octaédral (`export/impostor.py`) générés depuis le master.
   **Chaque variante + le master passent le gate** avant livraison.

---

## 6. Les trois préoccupations qui coexistent

> **Contrat de coexistence** : un seul pipeline d'asset, plusieurs profils. Le
> vent est *autorisé une fois* depuis le graphe dans des attributs portables ;
> chaque moteur consomme les **mêmes** attributs, seul le shader diffère. La
> forêt est le **même** master arbre-unité, dispersé. Le photoréalisme est le
> master pleine fidélité ; les profils ne font qu'**ajouter** (compression/KTX2)
> ou **retrancher** (Unreal strippe compression/KTX2/transmission) — jamais
> changer le sens de base du matériau.

### 6.1 Vent (défaut = attributs-sommets hiérarchiques, Crysis/GPU-Gems)

Trois paliers, calqués sur la décomposition global/branch/leaf de SpeedTree :

- **Tier 0 GLOBAL (tronc)** — balancement basse fréquence de tout l'arbre ;
  déplacement ∝ hauteur au-dessus du collet, puis renormalisé sur une sphère
  pour que le tronc ne s'étire pas ; pivot = collet à l'origine locale.
- **Tier 1 BRANCH (primaires)** — chaque branche oscille autour de son pivot
  (`TEXCOORD_1` = `parent.position + sag_offset`), amplitude ~ `1/stiffness`
  (épais = bouge à peine, fin = fouette), phase désynchronisée par branche.
- **Tier 2 DETAIL (rameaux + feuilles, `leafMask=1`)** — flottement par feuille
  (ondes triangulaires lissées le long de la normale), chaque feuille décalée par
  sa phase → scintillement de canopée.

**Encodage (contrainte dure)** : `COLOR_0 = (PHASE, STIFFNESS, LEAF_MASK)` VEC3
float ; `TEXCOORD_1 = pivot` VEC3 ; (option `TEXCOORD_2 = (wind_tier, branch_length)`).
**Jamais** d'attribut `_underscore`. **Dérivation FSPM** : `PHASE` = hash d'un id
**stable par axe** (`axis_node_ordinal`, jamais `node_index` global qui
s'entrelace entre chaînes) ; `STIFFNESS` = `clamp((diameter - d_min)/(d_max - d_min))`
calibré sur la plage réelle (~1.5–8.6 cm, lue par-arbre) ; `WIND_TIER` =
`min(2, axis_order)`.

**Consommateur de référence** (livré, `edit/static/wind.js`) : injection vertex
three.js `Material.onBeforeCompile` lisant `COLOR_0` + `TEXCOORD_1`, pilotée par
`uTime/uWindDir/uGustStrength`. **Interaction** : `uImpactPoints[]` ajoute un
déplacement radial local qui décroît avec la distance et ∝ `1/stiffness` —
frôler un arbre pousse les rameaux fins qui rebondissent. Sous
`EXT_mesh_gpu_instancing`, chaque instance porte un offset de phase/temps (pas de
balancement synchronisé).

**Voie skin (opt-in, hero only, `export/gltf/_skin.py`)** : un joint par chaîne
`is_main_axis` maximale (`_collect_chains`), ≤4 poids/sommet depuis la continuité
de rayon pipe-model, IBM = transform inverse de la pose de repos, clips TRS de
balancement bakés. Joue **sans aucun shader custom**, portable partout — réservé
à un arbre vitrine, **jamais** la forêt.

**Bonus Unreal (différé, gated)** : texture Pivot-Painter-2 — nécessite de
découper les tubes soudés en éléments par-branche, donc **hors des milestones
numérotés**, derrière un flag Unreal-first ; la voie pivot par-sommet obtient le
même mouvement sans cette chirurgie.

### 6.2 Forêt (le même master arbre-unité, dispersé)

**Émission (le fix phare)** : chaque arbre comme **mesh-unité à son origine
locale** (collet à `(x,0,z)`) + buffer `EXT_mesh_gpu_instancing` T/R/S. Remplace
l'actuel `write_glb_forest` qui bake les sommets-monde par arbre. **Granularité**
: configs identiques → mesh partagé + buffer multi-instances ; topologie unique →
node instancé de count 1 portant juste son transform. **Batching** : *un* matériau
par espèce via un atlas packé (`KHR_texture_transform`) — l'instancing ne batche
que mesh+matériau partagés. Métadonnées par instance via `EXT_instance_features`
(`_SPECIES,_SEED,_AGE`, offset de phase de vent).

**Mapping moteur** : three.js `InstancedMesh`, Unity glTFast → BRG/GPU-Resident
Drawer, Unreal → HISM/ISM, Cesium 3D-Tiles-Next reconstruisent tous depuis
arbre-unité + transforms. **Caveat Unreal** : GLTFCore ne construit **pas** de
HISM depuis `gpu_instancing` → le profil UNREAL_DCC aplatit les instances **ou**
émet une **liste sidecar** (CSV/JSON, style i3dm.export) pour l'outillage
foliage/PCG.

**Note overdraw** : le coût dominant moderne est l'**overdraw + virtual shadow
map**, pas les draw calls. Switcher tôt sur l'impostor ; garder peu de pages
d'atlas. Fusionner trop agressivement en un draw instancié peut *empirer*
l'overdraw sur GPU immediate-mode (à documenter).

### 6.3 Photoréalisme (le master pleine fidélité)

- **Feuilles** — lame **géométrique courbée/pliée** (`geom/leaf_blade3d.py` loft
  l'outline 2D existant + nervure médiane + courbure transverse) pour hero/gros
  plan : silhouette correcte, auto-ombrage, courbure qui capte le contre-jour,
  **majoritairement opaque** → tue l'overdraw et le coût d'alpha-test. Cartes
  `alphaMode:MASK` + `doubleSided` pour LOD moyens/lointains et l'herbe. Pour les
  cartes : **mips coverage-preserving + dilatation d'alpha** (sinon les lames
  fines s'érodent et halo sombre à distance) ; alpha-to-coverage sous MSAA au
  runtime ; **jamais BLEND** dans une canopée qui s'interpénètre.
- **Contre-jour** — masque thickness/translucence (lame claire, nervures/médiane/
  pétiole sombres) en alpha de la texture diffuse-transmission + poids par-sommet,
  consommé par les voies subsurface par-moteur. `KHR_materials_diffuse_transmission`
  émis en métadonnée prospective ; `KHR_materials_specular` ajoute la cuticule
  brillante. transmission+volume réservés aux *vrais* props translucides solides.
- **Écorce** — PBR opaque single-sided. Normale tangent-space bakée depuis un
  champ de hauteur **propre** (Sobel/Scharr, jamais depuis une photo éclairée) ;
  garder le signe `(-)` sinon les crêtes deviennent des rainures ; renormaliser
  après scaling ; exposer la force via `normalTexture.scale`. `_textures.py` étend
  pour émettre une **hauteur par espèce** (pas que l'albédo). `TANGENT` explicite
  (MikkTSpace). `Internode.birth_time` + le gradient `bark_blend` (sur `COLOR_1`)
  donnent une teinte d'écorce graduée par âge.
- **Packing PBR (détail décisif)** — ORM `O→R / Rough→G / Metal→B` ; ORM et
  normal **LINÉAIRE** (Blender Non-Color), seuls baseColor/emissive **sRGB** ; ne
  **pas** baker l'AO dans baseColor (double assombrissement). Valider les îlots UV
  miroités avec le `NormalTangentMirrorTest` de Khronos.
- **Saisons/santé** — `KHR_materials_variants` (printemps/été/automne/mort)
  réutilisant la machinerie de caducité (`Leaf.state ACTIVE/SENESCENT/ABSCISSED`)
  — bien plus portable que `KHR_animation_pointer` (plugin-only/expérimental).
  L'impostor utilise `KHR_materials_unlit` pour lire l'atlas baké sans
  ré-éclairage.

---

## 7. Décisions transverses

| # | Décision | Choix | Pourquoi (alternative rejetée) |
|---|---|---|---|
| D1 | Où vit la translucence | Masque thickness + shaders par-moteur ; `diffuse_transmission` = métadonnée | RC non supportée nulle part en 2026 → feuilles plates partout (vs. dépendre de l'extension) |
| D2 | Mécanisme de vent primaire | **Attributs-sommets** par défaut + seule voie forêt ; skin = hero only | Le skin coûte bones×instances + 1 draw/arbre (vs. skin par défaut) |
| D3 | Encodage des attributs vent | `COLOR_0=(phase,stiffness,leafMask)` + `TEXCOORD_1=pivot`, float ; teinte → `COLOR_1` | three.js/Unity **droppent** les `_underscore` (vs. `_PHASE/_STIFFNESS`) |
| D4 | Stratégie d'émission forêt | Arbre-unité à l'origine + `EXT_mesh_gpu_instancing` | Baker les sommets-monde tue instancing/batching/Nanite + fichiers linéaires |
| D5 | Granularité d'instancing | Mesh partagé si configs identiques, sinon **instance-of-one** | Chaque seed = topologie distincte → partage aveugle = arbres faux |
| D6 | Compression géométrie | `EXT_meshopt_compression` + quantization (WEB_UNITY) ; master non compressé toujours conservé | meshopt décode plus vite que Draco ; Unreal ne lit ni l'un ni l'autre |
| D7 | Philosophie LOD | 4 paliers discrets ; `MSFT_lod`+`MSFT_screencoverage` **web only** ; master intact pour Nanite | `MSFT_lod` ignoré des moteurs ; Nanite = Unreal-only, faible sur cartes alpha |
| D8 | Atlas / matériaux par espèce | 1 set d'atlas (baseColor sRGB + normal lin +Y + ORM lin) ; `KHR_texture_transform` | L'instancing ne batche que mesh **et** matériau partagés |
| D9 | Couleur / ORM / tangents | ORM `O→R/Rough→G/Metal→B` ; ORM+normal linéaire ; `TANGENT` VEC4 OpenGL +Y | sRGB sur data-texture = bug n°1 ; normal DirectX -Y = vert inversé concave |
| D10 | Représentation feuille hero | Lame **géométrique** courbée (LOD0) ; cartes alpha (moyen/lointain) | Coût dominant = overdraw, pas triangles ; lame 3D lit le contre-jour, évite l'alpha-test |
| D11 | Impostor | **Hémi**-octaédral 12–16² ; BaseColor+Normal+Depth ; quad + `KHR_materials_unlit` ; backend GL headless | Full-octa gaspille la moitié de l'atlas ; matplotlib ne fait pas le hors-écran multi-angle |
| D12 | Autorité « supporté » | Gate Validator Khronos + round-trip 4 moteurs, rejoué par version | Les tables de support dérivent à chaque release |

---

## 8. Plan d'implémentation (ordonné par valeur/effort)

> **Resequencing vs. #53.** #53 ordonne *look d'abord* (normal maps → SSS → ORM →
> … → instancing/vent à la fin). Ce plan met **la forêt d'abord** (P0, quelques
> jours, ROI le plus haut, indépendant de tout le travail texture), puis le
> **vent** (P1, car son émission de `TANGENT` est un **prérequis** des normal
> maps), puis les **matériaux** (P2). Chaque milestone est indépendamment
> livrable et testable.

| ID | Titre | Livrable | Dépend de | Effort | Validation |
|---|---|---|---|---|---|
| **P0** | Fix instancing forêt | Réécrire `write_glb_forest` → `export/instancing.py` : arbre-unité à l'origine (Y-up, m) + buffers T/R/S `EXT_mesh_gpu_instancing` + `EXT_instance_features` ; partage de mesh si configs identiques, sinon instance-of-one ; `extensionsUsed` set | — | **M** (2-3 j) | Validator OK ; round-trip trimesh + three.js : arbres bien placés ; golden sur le nb d'instances ; taille **sous-linéaire** pour espèces répétées |
| **P1** | Contrat de vent par-sommets + shader de réf | `geom/wind.py` (phase/stiffness/tier/pivot) ; élargir `Primitive` (tangents, color1, wind/pivot) ; estamper `COLOR_0`+`TEXCOORD_1` dans `tubes.py`/`leaves.py` ; teinte → `COLOR_1` ; **émettre `TANGENT`** ; boucle Attributes data-driven dans `gltf.py` ; `edit/static/wind.js` (onBeforeCompile) | P0 | **L** (1–1.5 sem) | Validator OK ; viewer montre le balancement hiérarchique avec bonne hiérarchie de raideur ; golden sémantique `COLOR_0` + présence `TANGENT` ; round-trip Unity confirme `COLOR_0` conservé si matériau le consomme |
| **P2** | Master photoréaliste : lame géo + normal/ORM + couleur | `geom/leaf_blade3d.py` ; `geom/maps.py` (normal Sobel, ORM, masque thickness) ; étendre `_textures.py` (hauteur + nervures) ; étendre `Material` (maps + tags d'espace) ; `KHR_texture_transform` (atlas), `KHR_materials_specular`, `diffuse_transmission` (métadonnée), `KHR_materials_variants` (saisons) ; mips coverage-preserving + dilatation pour cartes | P1 | **L** (2–2.5 sem) | Validator OK ; `NormalTangentMirrorTest` propre ; round-trip Blender/Cycles + Unreal non compressé : contre-jour via subsurface natif du masque ; check visuel ORM/normal linéaires |
| **P3** | Profils cibles + harnais de validation | `export/profiles.py` + CLI `palubicki bake` : WEB_UNITY (gltfpack meshopt + quantization + KTX2 + gpu_instancing + extensions complètes) et UNREAL_DCC (non compressé + PNG + instances aplaties/sidecar + extensions import-safe) ; master toujours conservé ; `tests/export/test_gltf_validation.py` (Validator + round-trip en CI) | P0,P1,P2 | **M** (1–1.5 sem) | Master + 2 profils passent le Validator ; WEB_UNITY charge en three.js + Unity glTFast ; UNREAL_DCC importe proprement (GLTFCore) ; CI verte ; matrice de support = résultats round-trip réels |
| **P4** | Chaîne LOD discrète + impostor hémi-octaédral | `export/lod.py` (4 paliers via réduction Strahler/axis-order + élagage sous-arbres d'ordre élevé, `MSFT_lod`+`MSFT_screencoverage`, master gardé pour Nanite) ; `export/impostor.py` + backend GL headless (moderngl/pyrender remplaçant matplotlib), atlas BaseColor+Normal+Depth, LOD3 = quad + `KHR_materials_unlit` + blend 3-frames + parallax | P2,P3 | **L** (2-3 sem, inclut renderer headless) | Validator OK ; l'impostor matche la silhouette hero à distance sans clipping rasant à 12-16 frames ; switch LOD vérifié via `MSFT_screencoverage` ; attributs survivent à la décimation (vent `COLOR_0` encore présent en LOD1/LOD2) |
| **P5** | Vent skinné hero + interaction *(opt., différé)* | `export/gltf/_skin.py` : 1 joint/chaîne main-axis, ≤4 poids/sommet (continuité de rayon), IBM, clips TRS pour un hero tree ; re-pose runtime + `uImpactPoints[]` dans le shader | P1 | **M** (1–1.5 sem) | Validator OK ; hero joue le balancement en three.js/Blender/Unreal/Unity **sans shader custom** ; ≤4 influences/sommet ; aucun sommet sans bone qui s'effondre à l'origine |

**Valeur/effort** : P0 = ROI le plus haut (corrige le pire bug, débloque la forêt
web/Unity/Cesium, indépendant). P1 = look-signature mouvant + débloque P2
(TANGENT). P2 = levier photoréaliste central + un matériau batché par espèce
(prérequis pour que l'instancing paie). P3 = rend les assets réellement chargeables
partout + institutionnalise la leçon « les tables dérivent ». P4 = gros gain
champ-lointain mais back-loaded (le renderer headless est le plus gros risque
d'infra ; la forêt scale déjà via P0 sans lui). P5 = différé (mauvais outil à
l'échelle forêt).

---

## 9. Questions ouvertes (à trancher)

1. **Topologie par-arbre vs. payoff d'instancing.** Chaque arbre étant seedé
   uniquement, combien d'instances partagent réellement un mesh dans une vraie
   forêt ? Si la plupart sont uniques, `EXT_mesh_gpu_instancing` dégénère en
   instance-of-one (gain de placement seulement, pas de dédup géométrie).
   **Faut-il un mode « species template »** (seed fixe par espèce, varié seulement
   par transform) pour que le vrai instancing paie, ou la variété topologique
   par-instance est-elle une exigence produit ?
2. **Backend GPU headless.** Quel backend (moderngl / pyrender / EGL-OSMesa) est
   viable dans la CI/dev macOS pour le bake multi-angle de l'impostor ? C'est le
   plus gros risque d'infra et il **gate tout P4**. Le bake d'impostor est-il
   acceptable en **étape dev-machine-only** si la CI ne peut pas faire de GL headless ?
3. **Source de vérité des textures/atlas.** `_textures.py` n'émet que l'albédo.
   On (a) étend les générateurs procéduraux pour synthétiser aussi hauteur +
   masques de nervures (garde le déterminisme seedé), ou (b) on accepte des
   textures externes authorées par espèce (plafond photoréaliste plus haut) ?
4. **Portée du gate de validation.** Le round-trip 4 moteurs est-il automatisable
   en CI, ou intrinsèquement une checklist manuelle par release ? Unreal/Unity
   sont lourds à faire tourner headless — si seuls three.js + Blender + Validator
   sont CI-automatisables, comment garder honnêtes les affirmations Unreal/Unity
   entre passes manuelles ?
5. **Fidélité de l'interaction de vent.** `uImpactPoints[]` est un confort à
   l'échelle forêt. L'interaction runtime joueur/projectile est-elle réellement
   dans le scope des consommateurs, ou le balancement ambiant suffit-il ? (Décide
   si le travail d'interaction de P5 est justifié.)
6. **Saisons : `KHR_materials_variants` vs. ré-export par pas de temps.** Les
   consommateurs veulent-ils des saisons discrètes sélectionnables (variants) ou
   une saison continue simulée (ré-export par `clock.t`) ?

---

## 10. Section README proposée (« first-class »)

À insérer après la section *Usage* :

```markdown
## Export & assets 3D

La sortie de base est un `.glb` (glTF 2.0 binaire) ouvrable dans n'importe quel
viewer. Au-delà, palubicki vise une **fabrique d'assets** : un master canonique
par arbre + des profils cibles (web/Unity vs. Unreal/DCC), avec rig de vent et
forêts instanciées.

- Référence technique : `docs/render-pipeline.md`
- Conception & plan : `docs/export-pipeline-design.md`
- Suivi : épic GitHub #53

palubicki bake oak.glb --profile web      # meshopt + KTX2 + instancing + LOD
palubicki bake oak.glb --profile unreal   # non compressé + PNG + import-safe
```

---

## 11. Mapping vers l'épic #53

#53 reste l'épic ; ce plan **réordonne et corrige** ses cases :

- **Ajouter à #53** : (a) la correction « `diffuse_transmission` est métadonnée,
  pas défaut » ; (b) « `MSFT_lod` web-only, LOD natif moteur » ; (c) le besoin
  d'un **`TANGENT` explicite** comme prérequis des normal maps ; (d) le modèle
  **master + profils** ; (e) la **subtilité instance-of-one** ; (f) le **backend
  GL headless** comme dépendance/risque de l'impostor.
- **Réordonner** : la case *GPU instancing* (aujourd'hui « nice to have v2+ »)
  devient **P0** ; *wind authoring* devient **P1** (avant les matériaux, à cause
  de TANGENT).
- **Sous-issues suggérées** : une par milestone P0…P5 (l'approche « 1 PR par
  workstream » de #53 tient toujours).
