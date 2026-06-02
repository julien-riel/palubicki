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

### Driver saisonnier + réponses à l'ombre

1. **#65 — phénologie graduée** · remplacer l'interrupteur binaire
   `annual_growth_period` par une rampe (courbe `year_fraction` en MVP,
   degrés-jours en *nice-to-have*). Généralise la fenêtre de #10 ; **la floraison
   (#11) lira le même driver**, donc le poser avant d'empiler le saisonnier.
   **Coordonne avec #61 (livré)** : la caducité saisonnière lit déjà la fenêtre
   binaire `annual_growth_period` ; #65 doit reprendre le *même* déclencheur de
   sénescence (entrée en dormance) quand il transforme la porte binaire en rampe.
2. **#63 — évitement d'ombre à l'initiation** · réduire l'**émission** de
   latéraux à l'ombre (pas seulement élaguer après — `shade_mortality` reste).
   Réutilise la machinerie de pondération de qualité (#3). Réagit au champ
   lumineux **corrigé par #62 (feuillus ; conifères via #7, livré)**. Levier
   d'initiation bon marché ; compose avec #56.
3. **#64 — mémoire mécanique du bois** · bois de réaction / redressement /
   raidissement sous charge intégrés dans le temps (#10 dispo), au lieu d'un sag
   statique recalculé à chaque pas. Charge-driven, complément de #34 (âge-driven).

### Changement de moteur profond

4. **#56 — forme émergente : variante shadow-propagation (Palubicki 2009)** · 2ᵉ
   backend d'exposition (BHse reste le défaut) : la silhouette (cône conifère,
   fût clair) **émerge** de l'auto-ombrage + dominance apicale au lieu d'être
   prescrite par l'enveloppe `cone`. Compose avec #62 (lumière feuillus correcte)
   et #63 (levier d'initiation). Le plus profond du backlog ; tranche d'abord le
   compromis dirigeable-vs-émergent.

### Nouveaux modes orthogonaux (gros, n'altèrent pas le pipeline ligneux)

5. **#11 — croissance déterminée + fleurs + inflorescences** · bundle cohérent
   (un apex se **détermine** en fleur ; une inflorescence est un arbre de pousses
   déterminées). Lit le driver saisonnier (#65). Débloque forbs, fruits, et un
   2ᵉ déclencheur sympodial propre.
6. **#12 — tallage + méristèmes intercalaires (graminées)** · nouveau mode de
   croissance (zone basale, tallage depuis le collet) ; architecturalement
   orthogonal, aucun code ligneux à toucher.
7. **#44 — vignes / lianas** · obstacle comme **attracteur** (aujourd'hui
   purement répulsif) + thigmotropisme + état cherche/accroché. Réutilise
   `sim/obstacles.py`. Seulement si scènes de paysage avec structures.

### Piste parallèle — apparence (orthogonale à la forme)

8. **#53 — qualité infographique (épopée rendu/export glTF)** · conception & plan
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
