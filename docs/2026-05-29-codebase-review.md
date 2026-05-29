# Revue de codebase : axes botanique & architecture logicielle

Date : 2026-05-29
Auteur : analyse Claude (Opus 4.8) — fan-out multi-agents + vérification directe du code

Objet : avis transversal sur `palubicki` selon **deux axes** demandés —
fidélité **botanique** et qualité **informatique / architecture logicielle**.
Ce document **complète et prolonge** :
- la revue [2026-05-27-simulation-review.md](./2026-05-27-simulation-review.md)
  (axe simulation/papier uniquement), et
- la [gap-analysis botanique](./botany/simulator-gap-analysis.md).

Il signale en particulier **deux constats nouveaux** que ni la revue du 2026-05-27
ni la gap-analysis n'avaient relevés (ou avaient mal qualifiés) :
le **compteur de phyllotaxie global** et les **conséquences réelles du cap
`n_substeps_max = 1`**.

Méthode : quatre agents de lecture en parallèle (dynamique de croissance ·
morphologie & espèces · architecture · tests/ingénierie), chacun tenu de citer
`fichier:ligne` et de **vérifier** les affirmations des docs contre le code.
Les deux constats [H] ci-dessous ont ensuite été revérifiés à la main.

État du code : `main` @ `0176e34`, **après** le Phase 1 « axe temps / phénologie »
([#10](https://github.com/julien-riel/palubicki/issues/10) / PR #23, commit
`7729537`). La revue initiale avait été faite sur l'état pré-#10 ; ce document a
été **revérifié et mis à jour** contre le code post-#10 (voir §5). Bilan : les
constats 1, 2 et 4 sont **inchangés** (`phyllotaxy.py` et `bh.py` non touchés par
#10), #10 a **renforcé** le constat 5 et **corrigé** le constat 7.

---

## 0. Synthèse exécutive

`palubicki` est un projet **remarquablement bien tenu** : ~7,2 K LOC de source,
~9,7 K LOC de tests (ratio test/source > 1), une doc botanique de niveau primer
scientifique, et une gap-analysis qui traque méthodiquement l'écart au réel. Fait
rare : le process et la documentation sont au niveau du code.

**Le verdict en une phrase** : *l'ingénierie et la compréhension botanique sont
excellentes, mais deux bugs de correction latents font que l'arbre produit est
moins fidèle que ce que le code — et les docs — laissent croire, et la suite de
tests (pourtant exemplaire) ne les attrape pas, parce qu'elle assertit des signaux
agrégés et non l'angle de divergence successif par axe.*

| # | Constat | Axe | Sévérité | Statut docs |
|---|---|---|---|---|
| 1 | Compteur de phyllotaxie **global**, pas par axe → spirale/décussé/distique brouillés sur l'arbre réel | Botanique (+ logiciel) | **H** | **Nouveau** (concédé en sourdine par un docstring) |
| 2 | Cap `n_substeps_max = 1` → l'allocation BH se réduit à une grille binaire dormant/actif ; `alpha_basipetal` quasi inerte | Botanique | **H** | Mal qualifié "Conforme" en 2026-05-27 |
| 3 | Phototropisme ≈ orthotropisme (gradient lumineux échantillonné seulement vers le ciel) | Botanique | M | Nouveau |
| 4 | Espèces qui ne "lisent" pas vrai (pin sans vrais étages, érable sans dents + textures chêne) | Botanique | M | Partiellement connu |
| 5 | Fan-out de la config + doublon `forest.py` (bug latent de divergence, **élargi par #10**) | Architecture | H | Nouveau (confirmé par #10) |
| 6 | Feuilles non *first-class* (synthétisées au render) → fuite sim→geom | Architecture | M | Connu (gap-analysis) |
| 7 | Ordre de passes temporelles (lengths→diameters→sag) imposé par convention, sans assertion comportementale | Architecture | L | Nouveau (revu après #10) |

**Top 3 des correctifs (meilleur ratio valeur/effort)** :
1. **Index de phyllotaxie par axe** (constat 1) — répare spirale + décussé +
   distique + le flag de diagnostic d'un seul coup.
2. **Un test au grain fin** : angle de divergence *successif par axe* — c'est ce qui
   aurait attrapé le constat 1 (le volet élongation+sag est, lui, déjà exercé par les
   goldens d'espèces, cf. constat 7).
3. **Loader config récursif** (constat 5) — supprime les blocs de coercion manuels
   et le doublon `forest.py`. #10 vient d'en démontrer le coût (~30 fichiers de test
   touchés + un 6ᵉ bloc de coercion) ; à faire **avant** le prochain pas de
   phénologie (feuilles-sur-nœuds, constat 6).

> **#10 (axe temps/phénologie) vient d'atterrir sur `main`.** Il ajoute une
> **horloge fractionnaire en années** (`sim/clock.py`), remplace `max_iterations`
> par `dt_years` + `max_simulation_years`, et introduit une **fenêtre de croissance
> saisonnière** `annual_growth_period`. C'est une **fondation propre et bien cadrée**
> (comportement par défaut inchangé) ; évaluation en §1.2, impact détaillé en §5.

---

## Axe 1 — Botanique

### 1.1 Ce qui est fidèle et fort

- **Colonisation par marqueurs conforme au manuel** (Runions/Palubicki) :
  compétition au bourgeon le plus proche, `Q = nb marqueurs gagnés`, direction
  optimale = somme normalisée des vecteurs unitaires, suppression dans `r_kill`
  (`sim/space_competition.py:60-111`). Perception en **vrai cône** (rayon +
  demi-angle), pas une simple sphère.
- **Récursion Borchert–Honda correcte** : passe basipète (post-ordre) pour
  `v_subtree`, passe acropète (pré-ordre) pour la distribution, split apical/latéral
  canonique `v·(λ·Q_main)/(λ·Q_main + (1−λ)·Q_lat)` (`sim/bh.py:38-129`).
- **Pipe model / da Vinci exact** : `r_parent = (Σ r_child^n)^(1/n)`, exposants
  2,25–2,49 selon l'espèce — pile dans la fourchette littérature 2,0–2,5
  (`sim/radii.py:38-44`).
- **Beer–Lambert + échantillonnage hémisphérique cosine-weighted** : abstraction
  légitime de l'interception lumineuse (`sim/light.py:176-285`).
- **Sag = vrai porte-à-faux linéarisé** : flèche ∝ charge·sinθ / diamètre²,
  charge = volume de bois en aval, tronc rigide sous un ordre donné
  (`sim/sag.py:89-135`). Les pointes ploient plus que les bases — qualitativement
  juste.
- **Bibliothèque de blades** (6 formes × 4 marges) : chaque espèce a une silhouette
  de feuille distincte ; seatage des latérales `cos β·g + sin β·radial`
  géométriquement sain (`geom/leaf_blade.py`, `sim/phyllotaxy.py:84-91`).

### 1.2 Simplifications défendables

- Marqueurs statiques, consommés et non régénérés — mécanisme standard de
  space-colonization pour un épisode de croissance.
- Phototropisme retombe sur un vecteur ciel fixe en l'absence de gradient.
- Sun/shade, teinte d'écorce, contrefort racinaire = **render-time** uniquement,
  hors couche sim.
- Élongation = sigmoïde par internode + target décroissant avec l'âge
  (`sim/elongation.py`) — courbe phénoménologique d'extension plausible.
- Déclencheur sympodial = stagnation de qualité plutôt que différenciation de l'apex
  (`sim/sympodial.py`) — acceptable pour les feuillus ligneux visés ; faux seulement
  pour les architectures déterminées/florifères, hors scope.
- **[#10] Fondation phénologique** : `Clock` fractionnaire en années
  (`sim/clock.py`), `Internode.birth_time` (en années) et fenêtre de croissance
  `annual_growth_period` [lo, hi) qui borne l'émission de nouveaux entrenœuds à une
  saison (`sim/simulator.py:68-71`). Abstraction **correcte** (`year_fraction` ∈ [0,1)
  comme coordonnée phénologique) et **bien cadrée** : par défaut (0,1) + `dt_years=1.0`,
  zéro changement de comportement — infrastructure opt-in qui ne mord que si
  `dt_years < 1.0`. Bon découplage déterminisme : le RNG reste salé par l'index de
  boucle entier, **pas** par `t` (commenté explicitement), donc les goldens tiennent.
  *Limites assumées* : fenêtre **rectangulaire** (binaire dans/hors saison), pas une
  courbe de vigueur graduée ; pas de débourrement physiologique (chilling/forçage),
  juste un calendrier fixe ; et le pendant **visible** d'un axe phénologique
  (déciduité, âge de feuille, marcescence) reste bloqué tant que les feuilles ne sont
  pas sur les nœuds (constat 6).

### 1.3 Problèmes réels

#### [H] Constat 1 — Le compteur de phyllotaxie est global, pas par axe

C'est **le** constat central. L'azimut de divergence est piloté par `node_index` :

- spirale : `base_azimuth = radians(divergence_angle_deg) · node_index`
  (`sim/phyllotaxy.py:71`)
- distique : `base_azimuth = π · node_index` (`sim/phyllotaxy.py:69`)
- décussé : parité `(π/2)·(node_index % 2)` (`sim/phyllotaxy.py:64-65`)

Or `node_index` est **un compteur monotone partagé par tout l'arbre**, et le
docstring du simulateur l'admet noir sur blanc :

> *« state.node_index assignments are interleaved across chains within each substep
> level (not all-of-A before any-of-B), so lateral phyllotaxy angles at
> substep-created nodes differ → small tree-shape drift »*
> (`sim/simulator.py:227-230`, post-#10)

**Conséquence** : le long d'un même axe anatomique, les nœuds consécutifs
**n'avancent pas** d'un Δ constant de 137,5° (spirale), n'alternent pas proprement
la parité 0°/90° (décussé) et ne basculent pas de 180° (distique) — parce que le
compteur saute du nombre de nœuds émis *ailleurs* dans l'arbre entre-temps. La
divergence effective entre nœuds successifs d'un axe devient `137,5° · Δ mod 360`
pour un Δ variable.

Donc les quatre ✅ du §5 de la gap-analysis (spirale, décussé, distique, whorled)
sont **corrects dans la fonction** mais **non livrés sur l'arbre**. C'est une
**régression** introduite par le refactor « step-major » (le chemin singleton
pré-refactor émettait les nœuds d'un axe de façon contiguë → Δ=1 → divergence
correcte).

Sévérité **visuelle** dépendante du mode :
- **Spirale** (chêne, bouleau) : impact réel mais subtil — on perd les parastiches
  comptables et l'espacement uniforme, mais les bourgeons restent répartis autour
  de l'axe. *C'est pourquoi personne ne l'a vu.*
- **Décussé** (érable) : **structurel** — deux nœuds adjacents de même parité font
  des paires coplanaires → la décussation s'effondre.
- **Distique** (sprays plagiotropes de conifères, via `distichous_on_plagiotropic`) :
  perte de l'alternance 2-rangs nette.

Bonus pervers : le diagnostic `divergence_angle_deg` (130–145°,
`sim/diagnostics.py`) flaggera l'arbre en échec **pour la mauvaise raison**.

**Le docstring sous-estime la gravité** (« small drift ») : pour décussé/distique,
ce n'est pas une dérive, c'est une rupture du motif.

#### [H] Constat 2 — Le cap `n_substeps_max = 1` réduit l'allocation BH à une grille binaire

Par défaut `n_substeps_max = 1` (`config.py:67`, aucun preset ne le surcharge), et
le simulateur applique `n_by_bud = {b: min(n, 1)}` (`sim/simulator.py:250`), alors
que `allocate()` calcule `v_total = α · Σ Q` (`sim/bh.py:23`) qui peut valoir 8
pour un bourgeon (cf. `tests/sim/test_bh.py`).

Tout le **magnitude** de l'allocation est donc jeté : il ne reste qu'un gate
« v ≥ 1 → +1 entrenœud, sinon DORMANT ». Le **contrôle apical** passe presque
exclusivement par le *sort* des bourgeons (dormant/actif) et par l'élagage — **pas**
par un taux d'extension différentiel. Un leader ne peut pas dépasser **en vitesse**
une latérale supprimée la même année. `alpha_basipetal` devient un bouton d'espèce
quasi inerte (il ne mord qu'au voisinage du seuil de dormance).

Nuance importante (à créditer) : le cap est **conforme au papier** (BHse fait bien
1 internode/bourgeon/cycle), et la revue 2026-05-27 le notait « Conforme ». Le
constat **nouveau** est la *conséquence* : avec le cap, deux des trois leviers de
forme du modèle BH (le taux d'extension et la magnitude `α`) sont neutralisés.
Et cela entre en **tension directe avec la philosophie de design du projet**
(« réalisme plutôt que papier-strict ») — le commentaire du code justifie pourtant
le cap par *« Paper BHse »*, soit l'option minimale du papier. **À trancher
consciemment** (voir §4).

#### [M] Constat 3 — Phototropisme ≈ orthotropisme (redondance)

Le « gradient lumineux » n'échantillonne que l'hémisphère autour de la direction du
ciel (`sim/light.py:211-285`). Ciel dégagé ⇒ tous les `T_k ≈ 1` ⇒ le gradient
pointe ≈ vers le haut. Il ne peut quasiment **jamais** pointer latéralement vers
une trouée. Donc `w_phototropism` **duplique en pratique** `w_orthotropy` : un arbre
de lisière ne peut pas se pencher vers la lumière, une branche ne croît pas dans une
percée latérale. Trompeur, car tous les presets règlent `w_phototropism > 0` en
attendant un effet distinct. *Fix : échantillonner la transmission sur une sphère
complète pour le **gradient directionnel**, tout en gardant l'hémisphère ciel pour
le **scalaire** `light_factor` (qui, lui, est correct pour l'interception).*

#### [M] Constat 4 — Espèces qui ne "lisent" pas vrai

- **Pin** : pas de vrais étages. 5 latérales émises à *chaque* nœud
  (`sim/phyllotaxy.py:50-51,88`), sans rythme de pousse annuelle → hélice continue
  de branches plutôt que verticilles discrets ; aggravé par le constat 1.
- **Érable** : `leaf_shape: palmate` + `leaf_margin: entire` →
  étoile lisse type *Liquidambar* (il manque les **dents**, pourtant supportées par
  le code) ; pointe en plus sur les textures `proc:oak_leaf` / `proc:oak_bark`
  (`configs/species/maple.yaml`). La posture (décussé + sympodial) est, elle, bien
  réglée.
- Pas de **fascicules** d'aiguilles (pin/sapin).
- **Sapin** auto-étiqueté *« Not a faithful Abies model »* (`configs/species/fir.yaml`).

#### [L] Mineurs honnêtes

- Cône de perception des **jeunes latérales** trop étroit et aligné sur l'insertion
  (peut tuer des latérales d'emblée si les marqueurs tombent hors cône).
- Règle « demi-tour de la direction blendée ⇒ DORMANT » (`sim/simulator.py:291`) :
  garde-fou d'enveloppe **déguisé en biologie** (une vraie méristème tournerait,
  ne mourrait pas).
- `v_subtree` comme « qualité de branche » pour l'élagage confond **vigueur** et
  **taille** de sous-arbre.

### 1.4 Verdict botanique

La biologie qualitative qui émerge (dominance apicale, remplissage de couronne,
auto-ombrage, taper, ploiement) est crédible, et la compréhension botanique est de
très haut niveau. Mais la **fidélité fine** est plafonnée par deux détails
d'implémentation (phyllotaxie globale, cap BH) — **pas** par un manque de savoir
botanique. Le correctif du constat 1 est de loin le meilleur ratio réalisme/effort.

---

## Axe 2 — Informatique / architecture logicielle

### 2.1 Ce qui est franchement bien conçu

- **Le layering est réel, pas décoratif.** `sim/` n'importe `geom/export/render`
  qu'**une seule fois** (import paresseux dans `sim/diagnostics.py`, et c'est
  justement la fuite du constat 6) ; `export/` ne connaît que le type neutre `Mesh`
  (`geom/mesh.py:32`). Le contrat « sim n'a ni géométrie ni glTF » tient.
- **Modèle de données identity-safe par construction** : `Bud/Node/Internode` en
  `@dataclass(eq=False)` (`sim/tree.py:17,29,44`) ; les dicts d'algos clés sur
  `id()` sont **transients par appel** (accumulateurs de traversée), zéro risque
  d'aliasing.
- **Le simulateur est un pipeline décomposé, pas un god-loop** : `_iteration_step`
  lit comme une séquence nommée (light → mortalité → marqueurs → qualité →
  croissance → kill → élagage → dynamique temporelle), chaque mécanisme dans son
  module derrière son `cfg.X.enabled`. `growth_direction` est une **fonction pure**
  (`sim/tropisms.py:12`).
- **Déterminisme par design** : aucun `np.random.seed()` global ; tout passe par
  `SeedSequence([seed, salt, iteration, node_index])`. Reproductibilité
  parallèle-safe comme **propriété**, pas comme convention.
- **Éditeur schema-driven** : `edit/schema.py` introspecte les dataclasses via
  `fields()` + `get_type_hints()` et les métadonnées `ui` — le JS ne code en dur
  aucun nom de paramètre. Obstacles via `Protocol`. Dépendances optionnelles isolées
  proprement (`RenderDependencyError`, hints d'install).

### 2.2 Dette réelle

#### [H] Constat 5 — Fan-out de la config + doublon `forest.py`

Ajouter/renommer **un** paramètre imbriqué touche : la dataclass, `__post_init__`,
`_SECTION_TYPES`, **les blocs de coercion manuels** de `load_config`, **une copie
quasi identique** dans `forest.py:45-53`, une **trentaine** de fichiers de test et
les 5 YAML. Pire : la copie de `forest.py` est un **sous-ensemble strict** — elle
coerce `sympodial` / `shade_mortality` / `elongation` / `branch_angle_by_order`
mais **pas** `bud_break_bias` **ni** (depuis #10) `annual_growth_period`. **Bug
latent** : un preset qui poserait l'un de ces deux en dict casserait en mode forêt
mais pas en mono-arbre.

**#10 est la démonstration grandeur nature de ce fan-out.** Remplacer
`max_iterations` par `dt_years` + `max_simulation_years` (+ renommer
`tau_iterations` → `tau_years`, ajouter `annual_growth_period`) a touché ~30 fichiers
de test + 5 YAML + `cli.py` + `config.py`, et a **ajouté un 6ᵉ bloc de coercion
manuel** (`config.py:647-653`, pour `annual_growth_period`) — sans le répliquer dans
`forest.py`, d'où l'**élargissement** du bug latent ci-dessus.

*Fix moyen-invasif : un loader récursif dataclass-aware (parcourir `fields()`,
récurser dans les champs de type dataclass) effondre tous les blocs + le doublon en
une fonction.*

#### [M] Constat 6 — Feuilles non *first-class*

Les feuilles sont synthétisées au render (`geom/leaves.py`), pas stockées sur les
nœuds — c'est **exactement** la cause de l'unique fuite sim→geom
(`sim/diagnostics.py` rappelle dans `geom.leaves._collect_foliage_sites`). Bloque
déciduité / âge de feuille / phénologie. **Coûteux** mais le modèle est assez propre
pour l'absorber. La gap-analysis le nomme déjà « le plus gros gap architectural ».
*Séquence (validée par #10)* : l'horloge calendaire est **faite** — #10 a livré
`Clock` + `birth_time` + fenêtre de croissance **sans** toucher aux feuilles, comme
prévu. La **migration des feuilles sur les nœuds est désormais le prochain pas** :
c'est elle qui supprime la fuite sim→geom et débloque déciduité / âge de feuille /
rendu saisonnier — le pendant **visible** de l'axe phénologique que #10 vient de
poser.

#### [L] Constat 7 — Couplage temporel implicite (revu après #10)

L'ordre `lengths → diameters → sag` est correct mais imposé par **commentaire**, pas
par types (`sim/simulator.py:494-495`), et #10 a **ajouté un 2ᵉ site d'appel** à
`_apply_temporal_dynamics` (vieillissement en saison dormante, `sim/simulator.py:71`)
qui repose sur le même ordre non vérifié.

**Correction par rapport au jet initial** : les 5 presets activent
`elongation.enabled: true` (`oak.yaml:15`, …) et `test_species_golden` les exécute en
`--years 10` — donc les **goldens d'espèces verrouillent bien** le pass temporel (un
réordonnancement changeant la géométrie ferait basculer leurs hash). Le jet initial
disait à tort « goldens élongation OFF » (ce n'est vrai que des goldens *ellipsoïde*).
La sévérité tombe donc à **[L]** : le résidu réel est que ces hash sont **opaques** et
**hors matrice CI** (cf. bloc « CI »), et qu'aucun test **comportemental** n'assertit
explicitement le contrat lengths→diameters→sag. *Fix léger : une assertion
comportementale (longueur monotone vers le target, sag croissant avec la charge)
plutôt qu'un hash.*

#### [M/L] CI & craftsmanship

- Un seul OS (Ubuntu) sur la matrice py3.11/3.12/3.13 ; **pas de gate de couverture**
  (`pytest-cov` tourne mais aucun `--cov-fail-under` → couverture mesurée puis jetée).
- Le tier golden/`pinned` est **hors matrice CI** : les régressions géométriques ne
  sont attrapées que localement.
- Taxonomie `pinned`/`slow` incohérente : le `-m "not pinned"` documenté
  (`pyproject.toml:48`) ne désélectionne **pas** tous les tests bit-exact (certains
  ne sont marqués que `slow`).
- Type hints ~72 %, docstrings de fonctions ~34 %, pas de mypy/pyright ; `scripts/`
  hors du périmètre ruff (un ternaire mort dans `scripts/regen_leaf_visuals.py:42`).

### 2.3 Qualité de test & ingénierie (à créditer)

≈650 tests (post-#10), **comportementaux et non smoke** : `forks >= 4` pour le chêne vs `== 0`
pour le pin (`tests/integration/test_sympodial_emergence.py`), latérales plagiotropes
qui s'horizontalisent (`mean < 40°`), mur d'obstacle qui réduit la croissance
(`wall < 0.8·open`), oracles indépendants réimplémentés (aire signée, point-in-polygon
dans `tests/geom/test_leaf_blade.py`). Gestion d'erreurs propre : 69 `ConfigError`,
contrat d'exit-codes testé, **un seul** `except Exception` (annoté `# noqa`),
**zéro** TODO/FIXME/HACK. Déterminisme **prouvé** par un test qui relance des
sous-process avec `PYTHONHASHSEED` différents (`tests/geom/test_textures.py`).
C'est de la discipline de niveau production sur un projet auto-déclaré PoC.

### 2.4 Verdict architecture

Santé architecturale remarquable pour un projet de cette taille. La dette est
concentrée et nommable : le fan-out config (+ son bug latent forest), les feuilles
hors-nœuds, un ordre de passes imposé par convention. Rien de structurellement
pourri ; tout est réparable de façon incrémentale.

---

## 3. Le point de jonction des deux axes

L'observation la plus intéressante est **méta** : il y a un écart frappant entre la
rigueur du process et deux bugs de correction que la suite n'attrape pas. **Le
compteur de phyllotaxie (constat 1) en est l'exemple parfait** — un défaut purement
logiciel (compteur mutable global au lieu d'un ordinal par axe) aux conséquences
**botaniques** majeures, **invisible** aux tests *parce qu'ils* assertent des signaux
**agrégés/directionnels** (nb de forks, inclinaison moyenne) et **jamais** l'angle
de divergence successif le long d'un axe. La culture de test, centrée sur l'agrégat,
ne surveille pas au bon grain.

Le miroir est vrai côté docs : la gap-analysis est excellente mais légèrement
**optimiste** — plusieurs « ✅ DONE » sont « corrects dans la fonction » mais pas
« livrés sur l'arbre ». La leçon transversale : **ajouter des assertions au grain
fin** est ce qui réaligne les deux axes.

---

## 4. Recommandations priorisées

### Top 3 (meilleur ratio valeur/effort)

1. **Index de phyllotaxie par axe** (constat 1). Stocker un `axis_node_ordinal` sur
   chaque `Bud`/`Node` qui n'incrémente **que** le long de sa propre lignée d'axe, et
   le passer à `phyllotaxy.lateral_bud_directions(node_index=…)`
   (`sim/phyllotaxy.py:64,69,71`). Convertit spirale/décussé/distique/whorled de
   « correct dans la fonction » à « réellement correct sur l'arbre », répare l'érable,
   le pin, le sapin et le flag de diagnostic d'un seul coup. **Précondition** pour que
   toute autre espèce lise vrai.
2. **Test au grain fin** : une assertion sur l'angle de divergence *successif par
   axe* ≈ angle attendu du mode — l'instrument qui aurait attrapé le constat 1. (Le
   volet élongation+sag est déjà couvert par les goldens d'espèces, cf. constat 7.)
3. **Loader config récursif** (constat 5) : supprime les blocs de coercion manuels +
   le doublon `forest.py:45-53` et son bug latent, et rend tout futur paramètre
   imbriqué gratuit côté chargement. #10 vient d'en facturer le coût (~30 fichiers de
   test + un 6ᵉ bloc) ; à faire **avant** le prochain pas de phénologie
   (feuilles-sur-nœuds).

### Secondaires

4. **Gradient phototropique sur sphère complète** (constat 3) — découple
   `w_phototropism` de `w_orthotropy`, autorise le phototropisme de lisière/trouée.
5. **Pin : rythme de verticilles** (émettre la whorl une fois par flush, pas à chaque
   nœud) ; **érable : `leaf_margin: serrate`** + corriger les textures `oak_*`.
6. **CI** : un job « environnement épinglé » (numpy/Pillow exacts) qui exécute
   `-m "slow or pinned"`, + `--cov-fail-under`, + macOS sur la matrice.
7. **Promotion des feuilles en attributs de nœud** (constat 6) — l'horloge calendaire
   étant livrée (#10), c'est **le prochain pas** du bloc feuillage/phénologie : il
   supprime la fuite sim→geom et débloque déciduité / âge de feuille / rendu saisonnier.

### À décider consciemment (pas par défaut)

- **Cap `n_substeps_max = 1`** (constat 2) : le garder (papier-strict, étages
  prévisibles) **ou** laisser l'allocation BH moduler un vrai taux d'extension
  différentiel (réalisme du contrôle apical). Si on garde le cap, alors `alpha_basipetal`
  devrait être documenté comme quasi inerte, ou retiré des presets pour ne pas tromper.

### À ignorer volontairement (repris de la gap-analysis)

Anneaux annuels, stipules, architecture racinaire souterraine, notation florale,
dimension fractale comme contrainte, catalogue Hallé–Oldeman complet, contreforts
tropicaux, bascule phyllotaxie juvénile/adulte — invisibles au render ou faible
valeur/coût.

---

## 5. Note de mise à jour — #10 « axe temps / phénologie » (PR #23)

Ce document a d'abord été rédigé sur l'état **pré-#10**, puis revérifié contre
`main` @ `0176e34` une fois #10 mergé. Ce que #10 a changé et l'effet sur la revue :

- **Ajouté** : `sim/clock.py` (horloge fractionnaire en années) ; config `dt_years`
  + `max_simulation_years` (propriété dérivée `num_iterations`) +
  `annual_growth_period` ; `Internode.birth_time` (remplace `birth_iteration`,
  `Bud.age` supprimé) ; élongation pilotée par `tau_years` ; fenêtre de croissance
  saisonnière dans la boucle forêt ; CLI `--years` / `--dt-years` ; tests
  `tests/sim/test_clock.py` + `tests/integration/test_phenology.py`. Conception :
  [design #10](./superpowers/specs/2026-05-29-time-phenology-axis-design.md).
- **Constats inchangés** : 1 (phyllotaxie — `phyllotaxy.py` non touché ; le docstring
  « interleaved across chains » survit, désormais `simulator.py:227-230`) ; 2
  (`bh.py` non touché, `n_substeps_max = 1` inchangé à `config.py:67`) ; 3 ; 4
  (presets non modifiés côté morphologie).
- **Constat 5 renforcé** : #10 est la preuve du fan-out (un 6ᵉ bloc de coercion
  manuel ; ~30 fichiers de test migrés) et **élargit** le bug latent `forest.py`
  (`annual_growth_period` non coercé en mode forêt, au même titre que `bud_break_bias`).
- **Constat 7 corrigé et rétrogradé [M] → [L]** : les goldens d'espèces tournent
  élongation **ON** (`--years 10`), donc le pass temporel est verrouillé bit-à-bit ;
  le résidu est l'absence d'assertion *comportementale* et le statut hors-matrice de
  ces goldens.
- **Nouveau (positif)** : la fondation phénologique elle-même, évaluée en §1.2 —
  abstraction correcte, bien cadrée, opt-in ; le payoff visible attend les
  feuilles-sur-nœuds (constat 6).

---

## Références

- [docs/2026-05-27-simulation-review.md](./2026-05-27-simulation-review.md) — revue
  simulation/papier antérieure (axe botanique partiel).
- [docs/botany/simulator-gap-analysis.md](./botany/simulator-gap-analysis.md) —
  gap-analysis structurée §1–§11.
- [docs/botany/plant-structure.md](./botany/plant-structure.md) — primer botanique.
- Palubicki et al., 2009 — *Self-organizing tree models for image synthesis*,
  SIGGRAPH. <https://algorithmicbotany.org/papers/selforg.sig2009.html>
