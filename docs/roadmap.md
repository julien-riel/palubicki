L'ordre des issues sur github.

> Méthode de travail transversale : la **boucle empirique auto-correctrice**
> (poser → observer les diagnostics → corriger → recommencer jusqu'à ce que ça
> lise vrai) — [`mindset-boucle-empirique.md`](mindset-boucle-empirique.md).

## Fait

- #1 — harness de diagnostic (métriques d'arbre générées)
- #2 — phyllotaxie distique explicite (bourgeon unique, alternance 180°)
- #3 — biais de débourrement (acrotone / mésotone / basitone)
- #4 — blade de feuille paramétrique (forme + marge), avec suivi #18
- #8 — évasement racinaire à la base du tronc (expansion radiale + contreforts ondulés optionnels, variation par arbre) ; polish au rendu, couche sim intacte (PR #21)
- #9 — variation d'écorce mélangée par `Internode.diameter` (teinte jeune → mature → sénescente, COLOR_0 par sommet ; pilotée par le diamètre, couche sim intacte) (PR #22)
- #10 — fondation temporelle / axe phénologique : horloge en années fractionnaires (`sim/clock.py`), `max_iterations` → `dt_years` + `max_simulation_years`, `birth_iteration` → `birth_time`, `tau_iterations` → `tau_years`, fenêtre de croissance annuelle `annual_growth_period`, suppression de `Bud.age`. Contrat d'invariance : à `dt_years=1.0` les arbres sont bit-identiques (goldens inchangés) (PR #23)
- Outillage (hors issue) — config ruff + CI GitHub Actions + refactor du simulateur (PR #19)

## Reste à faire (dans l'ordre)

Revue transversale du 2026-05-29 (`2026-05-29-codebase-review.md`) — trois nouvelles priorités passent en tête du backlog existant.

1. ~~#24 — **bug phyllotaxie**~~ ✅ **FAIT** : l'azimut de divergence était piloté par un compteur `node_index` **global** (entrelacé entre chaînes depuis le refactor step-major), donc spirale / décussé / distique corrects *dans la fonction* mais brouillés *par axe sur l'arbre*. Correctif livré : un ordinal **par axe** (`Bud.axis_node_ordinal`) — le terminal hérite `parent+1`, les latéraux/réserves repartent à 0, le latéral promu (sympodial) hérite l'ordinal de l'axe parent ; `node_index` conservé pour le salage RNG / identité. Précondition levée pour que pin / érable / sapin « lisent » vrai.
2. ~~#25 — test au grain fin~~ ✅ **FAIT** (livré avec #24) : `tests/sim/test_phyllotaxy_per_axis.py` fait pousser de vrais arbres et asserte l'angle de divergence *successif par axe* + parité décussé/distique, mesuré dans le repère d'émission (jauge-exacte). Échoue franchement sur le code pré-correctif, garde contre la régression.
3. ~~#26 — loader config récursif~~ ✅ **FAIT** (PR #30) : les 6 blocs de coercion manuels de `load_config` + le doublon `forest.py` remplacés par un loader récursif unique `_coerce` (descend dans les champs dataclass, normalise les tuples avec cast int/float + déballage `Optional`, rejette les clés inconnues avec le chemin pointé ; types résolus via `typing.get_type_hints`). Bug latent corrigé : le chemin des overrides par-graine de `per_tree_config` ne coerçait **rien** (passage direct par `replace()`), donc un override `sim.bud_break_bias` (dict) ou `sim.annual_growth_period` (list) survivait non-coercé en mode forêt — le cas dict plantait même `__post_init__`. Les deux points d'entrée partagent désormais `_coerce`. Garde de régression : `tests/sim/test_forest_species.py::test_forest_override_coerces_bud_break_and_growth_period`. Dé-risque #20 et #14.
4. #20 — longueur d'internode pilotée par la vigueur (flux Borchert-Honda continu ; retire `age_factor` + le cap `n_substeps_max`). Rend les quantités de croissance émergentes plutôt qu'imposées. S'appuie sur #10 (fait) pour démêler le proxy itération-comme-temps.
5. #32 — sourcer les bornes de littérature de `MetricRanges` depuis un manifeste cité (`configs/literature.yaml`, par espèce + fallback global) + script `scripts/fetch_botany_sources.py` pour télécharger les PDF botaniques (cache gitignoré, valeurs curées à la main). Branche le flag ✓/✗ de `diagnose` sur des valeurs sourcées et **par espèce** — le maillon « valeurs de référence » de la boucle empirique auto-correctrice. S'appuie sur #1 (harness) ; outille directement la recalibration de #20.
6. #14 — promouvoir les feuilles en attribut de `Node` (`Leaf` + `LeafState`). Refactor architectural, débloque tout ce qui suit côté foliage. La fondation temporelle (#10) étant en place, `LeafState` peut intégrer `leaf_age` en années dès sa conception.
7. #6 puis #5, #7 — la suite foliage, construite sur #10 (fait) + #14 (donc `LeafState` conçu une seule fois).
8. #11, #12 — beaucoup plus tard. La phénologie (#10) étant posée, #11 (croissance déterminée + fleurs, événement saisonnier) n'est plus bloqué côté infrastructure temporelle.
