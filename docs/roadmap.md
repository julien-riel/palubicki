# Roadmap

Ce fichier fait foi pour la priorisation (pas l'ordre des issues GitHub). Il
décrit **ce qui reste à faire** ; l'historique du livré est dans git (commits,
PR) et dans la [matrice de support botanique](botany/code-support-matrix.md).

> **Méthode transversale — boucle empirique auto-correctrice** : poser → observer
> les diagnostics → corriger → recommencer jusqu'à ce que ça lise vrai
> ([`mindset-boucle-empirique.md`](mindset-boucle-empirique.md)).

## À faire (ordonné pour bâtir sur du solide)

Ordre établi pour **éviter le rework** : câbler sur les fondations déjà livrées
avant d'empiler ; rendre la lumière correcte **avant** ce qui y réagit ; poser le
driver saisonnier avant ce qui le lit ; garder les gros changements de moteur et
les nouveaux modes orthogonaux pour la fin.

> **#62 + #7 (vraie surface de lame/aiguille dans la grille LAI) — livré.**
> L'auto-ombrage lit l'aire réelle (`leaf_area_records`, partagée avec
> `total_leaf_area`) pour les **feuillus** (#62) **et les conifères** (#7) : le
> dépôt scalaire `light.leaf_area` par bourgeon terminal est retiré, remplacé par
> `light.needle_area_scale` sur la vraie aire d'aiguille (multiplicité de fascicule
> incluse). Coupler les conifères cassait le leader (la « coquille de canopée »
> uniforme le soutenait) ; la dominance apicale est donc **re-calibrée** dans #7
> (`lambda_apical` pin 0.65→0.85, sapin 0.88 inchangé) — géométrie d'aiguilles et
> calibration lumière réglées ensemble, goldens #48 re-pinnés une seule fois.

> **#55 (spray latéral cohérent — forme) — livré.** `spray_plane_enabled` réfère
> la plagiotropie **et** la base d'insertion radiale au plan de la branche-mère
> (normale figée au débourrement, héritée le long du frond) au lieu du plan XY
> mondial ; la plagiotropie n'est plus décalée par `axis_decay` aux ordres
> supérieurs. Actif sur `fir`/`pine` (goldens #48 re-pinnés). Diagnostic
> `out_of_plane_deviation_deg` (fir ordre-2 ~24°→12°). Le couplage lumière conifère
> (reporté de #62) a été livré séparément dans #7 (fascicules + re-calibration).

> **#65 (phénologie graduée — rampe saisonnière) — livré.** L'interrupteur binaire
> `annual_growth_period` devient un **trapèze d'activité `[0,1]`**
> (`sim/clock.py::phenology_activity`) : rampes `sim.growth_period_shoulder` au
> débourrement et à la cessation, plateau à 1.0. `shoulder=0` (défaut de **tous** les
> presets) reste **byte-identique** à la porte binaire — goldens inchangés, zéro
> re-pin. L'activité multiplie la longueur d'entre-nœud émise (multiplicateur **final**,
> après saturation + jitter, donc identité IEEE à `activity=1.0`) ; **source unique
> partagée** lue par la croissance, la sénescence #61 (même seuil d'entrée en dormance
> `activity==0`, jamais de dérive) et, à venir, la floraison #11. Diagnostics
> `mean_growth_activity` / `shoulder_internode_fraction` (lus sur les entre-nœuds
> réels → reflètent le `.glb`). **Latent dans les presets** : la croissance étant
> *par-itération* (pas par-an), démontrer la rampe exige `dt<1`, qui re-calibrerait
> birch ; la fonctionnalité est donc prouvée par un test d'intégration **semé**
> (`dt=0.25`, `shoulder>0`, 5 graines) plutôt que par un preset expédié. Degrés-jours
> (GDD), fenêtres wrap-around et sénescence graduée dans la rampe descendante différés
> (pas de plomberie température ; `dt` annuel ne résout pas le sous-annuel).

> **#63 (évitement d'ombre à l'initiation) — livré.** À l'émission, chaque latéral
> ne débourre ACTIF qu'avec la probabilité `1 − strength·(1 − light_factor)`
> (`sim/shade_avoidance.py::lateral_break_probability`, lue sur le bourgeon-mère via
> le champ lumineux #62/#7) ; sinon il démarre **RESERVE** (`dormant_reserve_buds`) :
> l'investissement latéral est **retenu** à l'ombre au lieu d'être seulement élagué
> après coup (`shade_mortality` reste, complémentaire — l'un retient, l'autre élague
> les survivants). Les latéraux retenus sont réactivables par la **réitération
> existante** (`activate_reserves_on_shed`, sur élagage d'une branche ombragée) —
> aucune nouvelle boucle lumière→réactivation (différée avec le re-flush #61).
> `sim.shade_avoidance.strength` ∈ [0,1] = fraction retenue à l'ombre pleine ; **off
> par défaut** (`enabled=False`) / `strength=0` / plein soleil ⇒ aucun tirage RNG,
> évolution **byte-identique** (goldens inchangés, zéro re-pin). Compose avec #3 à
> des étages distincts (le biais de position pondère la *vigueur* des latéraux
> débourrés ; #63 décide le *débourrement* — pas de double comptage). Diagnostic
> `lateral_reserve_fraction` (lu sur le graphe de bourgeons → reflète le `.glb`).
> **Latent dans les presets** (comme #65) : prouvé par un test d'intégration semé
> (chêne auto-ombragé, `dormant_reserve_count=0` + `shade_mortality` off pour isoler
> l'initiation), pas par un preset expédié.

> **#84 (audit du pipeline lumière) — livré.** Correctifs physiques appliqués :
> auto-ombrage de l'apex (#1, HIGH — le demi-pas de ray-march ne quittait pas la
> cellule du bourgeon ~43 % du temps, étouffant la dominance apicale), grille
> *scale-aware* dérivée de `voxel_edge_m`, bouton `wood_extinction_scale`, gradient
> de lumière centré, phototropisme sans repli +Y, décussé/verticillé sans terme
> spiral, mortalité d'ombre des dormants, réserves par-mode. Goldens régénérés
> (6 espèces + ellipsoïde + forêt V3), suite verte (935 passed). Les **métriques de
> croissance** (hauteur/tronc/couronne/bif) sont désormais **toutes en bande** ;
> les 8 hors-bande restants sont des **bugs de mesure** isolés dans #83. Limites
> assumées (non modifiées) documentées dans `realism-assessment.md` (C irradiance
> hémisphère, B bois partage `k`, F-résiduel lumière dans vigueur/shedding,
> A-rationale constantes liées au voxel).

### Justesse de calibration (fondation correcte avant d'empiler)

L'audit #84 a rendu le **champ lumineux** correct. Avant d'ajouter de nouveaux
mécanismes, on rend la **mesure** correcte (#83) puis on **verrouille** la justesse
botanique en CI (#87) — exactement la règle « rendre la lumière correcte avant ce
qui y réagit » appliquée à la calibration. Cette piste passe **devant** la mémoire
mécanique et le reste.

1. **#83 — bug de mesure des angles ordre-1** · `insertion_angle` dilué par la
   courbure intra-branche + bande `divergence` mal typée pour décussé/verticillé.
   Les **8 dernières métriques hors-bande** des 6 espèces (post-#84) sont *toutes*
   dues à ces deux défauts, et **intunables** (aucun preset ne les corrige). Pur
   correctif de diagnostic ; débloque une lecture *vraie* de l'état de calibration.
   **Gate tout le reste de cette piste.**
2. **#87 — garde-fou botanique en CI** · test multi-graines qui échoue si une
   espèce sort de ses bornes `literature.yaml` (pas seulement le hash de
   déterminisme). N'a de sens **qu'après #83** (les bandes mesurent enfin la
   réalité). Verrouille la justesse contre les régressions futures.
3. **#86 — activer + calibrer `shade_avoidance` par espèce** · 2ᵉ levier de densité
   de couronne (rétention à l'**initiation**), séparé de `shade_mortality`
   (élagage). Sort du piège de non-identifiabilité (même densité atteignable par
   parcimonie d'initiation *ou* élagage agressif, indistinguables). À faire une fois
   #87 en place pour attraper les régressions. Le vrai correctif (budget carbone
   source→puits) reste #66, fermé `NOT_PLANNED` — ceci est le proxy assumé.
4. **#85 — contrat `voxel_edge_m=0.04` + vérif finale** · *réduite* : le re-base sur
   la grille voxel + re-pin des goldens + mise-en-bande de la croissance sont déjà
   faits dans #84. Reste à **documenter le contrat** (changer `voxel_edge_m`
   décalibre `k_absorption`/`leaf_area_scale`/`needle_area_scale`) et à **vérifier
   « tout en bande »** une fois #83 réglé.

### Mémoire mécanique (intégrée dans le temps)

5. **#64 — mémoire mécanique du bois** · bois de réaction / redressement /
   raidissement sous charge intégrés dans le temps (#10 dispo), au lieu d'un sag
   statique recalculé à chaque pas. Charge-driven, complément de #34 (âge-driven).

### Changement de moteur profond

6. **#56 — forme émergente : variante shadow-propagation (Palubicki 2009)** · 2ᵉ
   backend d'exposition (BHse reste le défaut) : la silhouette (cône conifère,
   fût clair) **émerge** de l'auto-ombrage + dominance apicale au lieu d'être
   prescrite par l'enveloppe `cone`. Compose avec #62 (lumière feuillus correcte)
   et #63 (levier d'initiation). Le plus profond du backlog ; tranche d'abord le
   compromis dirigeable-vs-émergent.

### Nouveaux modes orthogonaux (gros, n'altèrent pas le pipeline ligneux)

7. **#11 — croissance déterminée + fleurs + inflorescences** · bundle cohérent
   (un apex se **détermine** en fleur ; une inflorescence est un arbre de pousses
   déterminées). Lit le driver saisonnier **#65 (livré)** via une fenêtre de
   floraison propre passée au **même** `clock.phenology_activity` (aucune nouvelle
   math de rampe). Débloque forbs, fruits, et un 2ᵉ déclencheur sympodial propre.
8. **#12 — tallage + méristèmes intercalaires (graminées)** · nouveau mode de
   croissance (zone basale, tallage depuis le collet) ; architecturalement
   orthogonal, aucun code ligneux à toucher.
9. **#44 — vignes / lianas** · obstacle comme **attracteur** (aujourd'hui
   purement répulsif) + thigmotropisme + état cherche/accroché. Réutilise
   `sim/obstacles.py`. Seulement si scènes de paysage avec structures.

### Piste parallèle — apparence (orthogonale à la forme)

10. **#53 — qualité infographique (épopée rendu/export glTF)** · conception & plan
    reséquencés dans [`docs/export-pipeline-design.md`](export-pipeline-design.md)
    (master canonique non compressé + profils cibles ; **la forêt d'abord, pas le
    look**). Sous-tickets P0…P5 indépendants, un PR chacun.
    **P0 ([#71](https://github.com/julien-riel/palubicki/issues/71)) livré** :
    l'export forêt émet l'**arbre-unité à son origine locale** (collet à `(x,0,z)`)
    + transform par instance — `EXT_mesh_gpu_instancing` (T + `_FEATURE_ID` espèce/
    seed via `EXT_instance_features`) quand des arbres partagent la même géométrie,
    sinon un node TRS « instance-of-one ». Plus aucun sommet-monde baké ; taille
    **sous-linéaire** pour les espèces répétées (`export/instancing.py` remplace
    l'ancien `write_glb_forest`).
    **P1 ([#72](https://github.com/julien-riel/palubicki/issues/72)) livré** :
    vent hiérarchique (Crysis/GPU-Gems) autorisé **une seule fois** depuis le graphe
    FSPM (`geom/wind.py`, lecture seule) dans un contrat d'attributs portable —
    `COLOR_0=(phase,stiffness,leafMask)`, `TEXCOORD_1/2=pivot+tier`, teinte
    d'écorce/automne déplacée sur `COLOR_1` — plus l'émission de `TANGENT` (VEC4,
    quasi-gratuite depuis le repère parallel-transport des tubes), **prérequis des
    normal maps de P2**. `phase` est hashée en repère local-arbre pour que les
    arbres identiques restent partageables sous instancing ; le pivot est localisé
    avec les positions. Shader three.js de référence (`edit/static/wind.js`,
    `onBeforeCompile`) câblé dans le viewer (toggle Wind). Validator Khronos
    0 erreur/0 warning (arbre, espèce composée, forêt).
    **P2 ([#73](https://github.com/julien-riel/palubicki/issues/73)) livré** :
    master photoréaliste PBR metallic-roughness portable. Cartes bakées depuis des
    champs *propres* procéduraux (`geom/maps.py` : normale tangent-space Sobel
    OpenGL +Y, ORM packé `O→R/Rough→G/Metal→B`, masque thickness/translucence en
    alpha) à partir de sources par-espèce (`_textures.py` : champs de hauteur
    d'écorce + nervures/médiane des feuilles). `Material` étendu (normal/ORM/
    occlusion/emissive/thickness + tags d'espace : baseColor/emissive **sRGB**,
    le reste **linéaire**, AO jamais dans baseColor). Lame de feuille **géométrique
    héro** (`geom/leaf_blade3d.py` : pli médian + recourbure, normales/​tangentes
    lissées) câblée par défaut sur les feuillus (chêne/​bouleau/​érable/​frêne) ;
    feuillage plat = chemin legacy byte-identique (empreinte (u,v) inchangée → grille
    de lumière intacte). Extensions câblées : `KHR_texture_transform` (atlas),
    `KHR_materials_specular` (cuticule), `KHR_materials_variants` (saisons),
    `KHR_materials_diffuse_transmission` (**métadonnée prospective** — RC, ignorée
    des moteurs en 2026, contre-jour réel via shaders subsurface par-moteur).
    Validator Khronos 0 erreur/0 warning (arbre, chêne/​érable héro avec maps). Suite :
    P3 profils + gate de validation
    ([#74](https://github.com/julien-riel/palubicki/issues/74)) →
    P4 LOD + impostor hémi-octaédral ([#75](https://github.com/julien-riel/palubicki/issues/75)) →
    P5 vent skinné hero ([#76](https://github.com/julien-riel/palubicki/issues/76),
    différé). À piquer en parallèle du travail de forme ci-dessus.

> **Suivi surgi de #61 (caducité, livré)** — *re-flush foliaire sur le vieux
> bois*. Les feuilles ne sont émises qu'à la naissance du nœud et jamais
> renouvelées ; sans re-flush printanier, la caducité à `dt=1.0` (résolution
> annuelle, sans saison) ne ferait qu'éclaircir la couronne, d'où des plafonds de
> durée de vie *inertes* dans les presets et le report du turnover des aiguilles
> persistantes. Prérequis d'un vrai cycle annuel décidu/persistant ; à coupler
> avec #65 (phase saisonnière partagée) et le débourrement des bourgeons.

> **Hors backlog actif** — #66 (budget carbone source→puits) fermé `NOT_PLANNED` :
> refonderait le moteur, frontière de conception assumée
> ([code-support-matrix.md](botany/code-support-matrix.md), réalisme fonctionnel).
