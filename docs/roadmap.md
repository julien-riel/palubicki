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

> **#83 (mesure des angles ordre-1) — livré.** Les deux métriques de diagnostic
> d'ordre-1 mesurent enfin ce que leurs bandes attendent (`sim/diagnostics.py`).
> **Insertion** : `insertion_angle_deg_vs_parent` n'est plus diluée par la courbure
> intra-branche — mesurée **au seul internode fondateur de chaque axe** (incoming
> d'ordre strictement inférieur = le point de branchement) ; la courbure intra-axe
> n'est plus mesurée (aucune bande ne la consomme). **Divergence** :
> `_divergence_angle_metrics` est désormais **par mode de phyllotaxie** — rotation
> inter-nœud de l'azimut de base modulo `360/k` (spiral 137,5° ; décussé 90°), et
> espacement intra-verticille **plus-proche-voisin** `360/k` pour le verticillé
> (pin ~62°, robuste à l'occupation du verticille là où la moyenne flappe 86–100°).
> Le mode est *threadé* depuis `cfg.phyllotaxy` (les latéraux ordre-1 utilisent
> toujours `cfg.mode`). Bandes `literature.yaml` re-dérivées sur la mesure
> **post-tropisme** (insertion globale `(50,90)` ; divergence : alterne `(130,145)`,
> décussé maple **+ ash ajouté** `(80,100)`, pin `(52,78)`). Goldens **inchangés**
> (aucun golden n'épingle la sortie diagnostic, zéro re-pin) ; deux **gardes lentes
> par-espèce** ajoutées (insertion + divergence in-band) pour fermer le trou
> « intunable-mais-vert » qui a laissé #83 passer. **Débloque la lecture vraie de
> l'état de calibration → #87.**

> **#87 (garde-fou botanique en CI) — livré.** `tests/integration/test_botanical_guardrail.py`
> simule chaque espèce sur les graines {0,1,2} et **échoue** si une métrique bornée
> dérive hors de sa bande `literature.yaml` (moyenne multi-graines vs bande, comme
> `diagnose --seed 0,1,2`). Moteur réutilisable `sim.diagnostics.check_bounds` /
> `gated_fields` (résout la convention de chemin `__orderN_mean`, single- &
> multi-graine). **Gated** = toute métrique bornée (hauteur, tronc, couronne,
> continuation, leader, Horton, divergence+insertion ordre-1) ; **advisory** = le
> reste (sans borne citée). ash : borné sur ses 3 bandes héritées (divergence
> décussée + insertion/Horton globales) ; bandes architecturales Fraxinus différées
> (absentes du manifeste). **Consolide** les 5 gardes mono-graine #83/#48/#7 (un
> balayage par espèce plutôt qu'un-par-métrique → moins de simulations lentes,
> notamment pin ~210-820 s/graine). Deux dérives mises **in-band** : chêne
> `shedding.quality_threshold` 0.15→0.08 (retient plus de brindilles ordre-1 →
> Horton 2.95→3.29) ; bouleau **bande** couronne 4.0→4.8 (la valeur 4.46 m est
> réaliste pour un *B. papyrifera* de 30 ans et `crown_radius` est une mesure
> *max-extent* chaotique — `rx` couple à la divergence, donc pas de réglage propre).
> Le golden chêne 10 ans est **inchangé** (le seuil de `shedding` ne mord qu'au-delà,
> la géométrie à 10 ans est identique) ; seul le pin d'aire foliaire est re-pinné
> (chêne +#87, et dérive bouleau/érable **préexistante** des commits geom). Seule la
> **moyenne** multi-graines est gardée (pas le par-graine : `crown_radius` max-extent
> et Horton sont trop bruités pour un seuil par-graine). **Marqué `slow`** : tourne
> dans la suite lente complète (locale / pré-merge), **pas** dans la matrice GitHub
> (`-m 'not slow'`) — ~15-45 min dominé par le pin. **Débloque #86.**

> **#86 (activer + calibrer `shade_avoidance` par espèce) — livré.** Le levier de
> rétention à l'**initiation** (#63, jusqu'ici dormant) est activé avec un `strength`
> par espèce **gradué sur la tolérance à l'ombre** : tolérantes `maple` 0.55 / `fir` 0.45,
> intermédiaires `oak`/`ash`/**`pine`** 0.40 / 0.40 / 0.35, pionnière **`birch` désactivée**.
> Les deux leviers de densité de couronne sont **co-réglés, pas empilés** : à chaque
> `strength` relevé, le `shade_mortality` de l'espèce est **détendu** (seuil ou pas) pour
> tenir la densité nette — sinon la rétention retire de l'auto-ombrage, **remonte la
> lumière** et fait **double-compter** la suppression à l'élagueur (sous-estime couronne /
> tronc / Horton ; vérifié — l'audit était une prédiction *confirmée*). Deux corrections
> *réalisme > papier-strict* : (1) **`pine` est intermédiaire** (Niinemets & Valladares
> ~3.2 ; USDA Silvics « intermediate »), pas « intolérante » comme le libellé du billet —
> donc au niveau `oak`/`ash`, pas avec `birch` ; (2) **`fir` `reactivation_count` 0→1**
> pour que ses réserves retenues forment une vraie banque réactivable (sinon pur
> éclaircissage, à rebours pour la plus tolérante). **`birch` désactivée** : sa canopée est
> si clairsemée (`total_leaf_area` ~10) qu'un `strength` ≥0.10 remonte la lumière, freine
> l'élagueur et pousse le `crown_radius` (max-extent chaotique) au-delà du plafond 4.8
> (4.46→4.90 à 0.10, 5.42 à 0.18) — elle reste le **plancher zéro** du gradient, golden
> **byte-identique** (pas de re-pin). Critère 3 prouvé par
> `tests/integration/test_shade_relief_differential.py` : à `strength` fixe et élagueur
> coupé, `lateral_reserve_fraction` **suit le champ lumineux** (l'initiation lit la lumière,
> pas l'élagage). La *réactivation* d'une réserve retenue est déjà couverte par le test
> unitaire #63 ; la vraie boucle lumière→réactivation reste différée (#61 re-flush) —
> empiriquement les nœuds ombragés qui retiennent une réserve n'ont guère d'enfant à
> élaguer, donc ces réserves dorment. Garde-fou **#87 vert** (6 espèces, graines {0,1,2},
> deux mécanismes actifs) ; goldens `oak`/`maple`/`fir`/`pine` re-épinglés (`birch`/`ash`
> inchangés ; `ash` n'a pas de golden).

> **#85 (contrat `voxel_edge_m=0.04` + vérif finale) — livré.** Le contrat de
> calibration implicite est rendu **explicite et découvrable** sur trois surfaces :
> commentaire dans le bloc `light:` des **six** presets, champ
> `LightConfig.voxel_edge_m` ([`config.py`](../src/palubicki/config.py)) et section
> dédiée **« Contrat de calibration »** dans
> [`realism-assessment.md`](botany/realism-assessment.md) avec la **procédure de
> re-calibration** (5 étapes). Fait physique posé : la profondeur optique par
> feuille vaut `k · aire / voxel_edge_m²` (dépôt `LAI = aire/volume_cellule`,
> `τ += k·LAI·step_len`, `step_len ≈ voxel_edge_m`) — donc **∝ 1/voxel_edge_m²** :
> changer la taille de voxel rescale **tout** l'auto-ombrage et décalibre les six
> espèces (`k_absorption` 0.45–0.65 ; `needle_area_scale` 0.5 sapin/pin ; aucun
> preset ne fixe `voxel_edge_m`, tous héritent du défaut 0.04). **Vérif finale** :
> #83 (mesure ordre-1) et #87 (garde-fou) livrés, le balayage `diagnose --seed
> 0,1,2` sur les 6 espèces **+** `test_botanical_guardrail.py` (**6 passed**, 958 s)
> sont **tout en bande** — les 8 hors-bande de #84 étaient bien des **artefacts de
> mesure #83** (insertion/divergence ordre-1 ✓ partout, p.ex. oak insertion
> 27,7°→74,4°, érable divergence 178°→90,9°), **zéro vraie dérive restante**.
> Documentation + vérification **uniquement** : commentaires seuls, **aucun
> changement de comportement**, goldens **byte-identiques** (zéro re-pin).

L'audit #84 a rendu le **champ lumineux** correct, #83 a rendu la **mesure**
correcte, #87 **verrouille** la justesse botanique en CI, et #85 **documente le
contrat** `voxel_edge_m=0.04` + acte la **vérif « tout en bande »** — la piste
**« Justesse de calibration » est close** (« rendre la lumière correcte avant ce
qui y réagit », appliqué à la calibration). Reste, au-delà de cette piste :

### Mémoire mécanique (intégrée dans le temps)

5. **#64 — mémoire mécanique du bois** · bois de réaction / redressement /
   raidissement sous charge intégrés dans le temps (#10 dispo), au lieu d'un sag
   statique recalculé à chaque pas. Charge-driven, complément de #34 (âge-driven).

> **#94 (cône conifère émergent) — livré.** Sous `sim.length_banking` (longueur
> latérale **pilotée par l'âge**), le sapin sous `exposure: shadow_propagation` +
> bornes neutres `half_ellipsoid` développe un **vrai cône** (`crown_monotonicity`
> +0.31 ovoïde → −0.77 cône ; `silhouette_drift` 0.37 → ~0.17 vs fir-BHse ; hauteur /
> couronne / tronc en bande, leader parfait) — la forme émerge de la compétition
> lumineuse + l'âge, **sans** enveloppe `cone`. Le 1er mécanisme (persistance à taux
> fixe) a échoué — la croissance de jeunesse-éclairée domine ; c'est la longueur
> **pilotée par l'âge** (jeune court, vieux long) qui renverse l'ovoïde. Garde
> d'établissement au shedding (la base bankée n'est pas élaguée pour l'ombre). Défaut
> OFF ⇒ **byte-identique**. Le preset conifère reste `bhse` (golden gelé) ; l'émergence
> est prouvée par `tests/integration/test_emergent_cone.py`. Voir `realism-assessment.md`
> §forme émergente.

### Nouveaux modes orthogonaux (gros, n'altèrent pas le pipeline ligneux)

6. **#11 — croissance déterminée + fleurs + inflorescences** · bundle cohérent
   (un apex se **détermine** en fleur ; une inflorescence est un arbre de pousses
   déterminées). Lit le driver saisonnier **#65 (livré)** via une fenêtre de
   floraison propre passée au **même** `clock.phenology_activity` (aucune nouvelle
   math de rampe). Débloque forbs, fruits, et un 2ᵉ déclencheur sympodial propre.
7. **#12 — tallage + méristèmes intercalaires (graminées)** · nouveau mode de
   croissance (zone basale, tallage depuis le collet) ; architecturalement
   orthogonal, aucun code ligneux à toucher.
8. **#44 — vignes / lianas** · obstacle comme **attracteur** (aujourd'hui
   purement répulsif) + thigmotropisme + état cherche/accroché. Réutilise
   `sim/obstacles.py`. Seulement si scènes de paysage avec structures.

### Piste parallèle — apparence (orthogonale à la forme)

9. **#53 — qualité infographique (épopée rendu/export glTF)** · conception & plan
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
