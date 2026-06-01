# Roadmap

Ce fichier fait foi pour la priorisation (pas l'ordre des issues GitHub). Il
décrit **ce qui reste à faire** ; l'historique du livré est dans git (commits,
PR) et dans la [matrice de support botanique](botany/code-support-matrix.md).

> **Méthode transversale — boucle empirique auto-correctrice** : poser → observer
> les diagnostics → corriger → recommencer jusqu'à ce que ça lise vrai
> ([`mindset-boucle-empirique.md`](mindset-boucle-empirique.md)).

## À faire (ordonné pour bâtir sur du solide)

Ordre établi pour **éviter le rework** : câbler sur les fondations déjà livrées
avant d'empiler ; rendre la lumière correcte **avant** ce qui y réagit ;
restaurer le filet de tests rouge tôt ; poser le driver saisonnier avant ce qui
le lit ; garder les gros changements de moteur et les nouveaux modes orthogonaux
pour la fin.

> **#62 (vraie surface de lame dans la grille LAI) — livré pour les feuillus.**
> L'auto-ombrage des feuillus lit l'aire de lame réelle (`leaf_area_records`,
> partagée avec `total_leaf_area`) au lieu d'un scalaire. Les **conifères** restent
> sur le dépôt scalaire `light.leaf_area` par bourgeon terminal : leur dominance
> apicale émerge de cette « coquille de canopée » et la coupler aux vraies aiguilles
> casse le leader (pin). Le couplage lumière des conifères est donc **plié dans #7**
> ci-dessous, où géométrie d'aiguilles et calibration lumière se règlent ensemble.

> **#55 (spray latéral cohérent — forme) — livré.** `spray_plane_enabled` réfère
> la plagiotropie **et** la base d'insertion radiale au plan de la branche-mère
> (normale figée au débourrement, héritée le long du frond) au lieu du plan XY
> mondial ; la plagiotropie n'est plus décalée par `axis_decay` aux ordres
> supérieurs. Actif sur `fir`/`pine` (goldens #48 re-pinnés). Diagnostic
> `out_of_plane_deviation_deg` (fir ordre-2 ~24°→12°). **N'a livré que la forme** :
> le couplage lumière conifère reporté de #62 reste à faire et est replié dans #7.

### Restaurer le filet conifère (#48 goldens tenus rouges)

1. **#7 — fascicules d'aiguilles** · aiguilles de conifères (réparties le long du
   rameau, #36) regroupées en fascicules de 2–5, posées sur le cadre de spray
   livré par #55. **Reprend le couplage lumière conifère reporté de #62** (vraie
   aire d'aiguille dans la grille LAI, avec re-calibration de la dominance
   apicale, qui doit se régler en même temps que la géométrie des aiguilles).
   Re-pin des goldens #48 une seule fois, avec les fascicules.

### Driver saisonnier + réponses à l'ombre

2. **#65 — phénologie graduée** · remplacer l'interrupteur binaire
   `annual_growth_period` par une rampe (courbe `year_fraction` en MVP,
   degrés-jours en *nice-to-have*). Généralise la fenêtre de #10 ; **la floraison
   (#11) lira le même driver**, donc le poser avant d'empiler le saisonnier.
   **Coordonne avec #61 (livré)** : la caducité saisonnière lit déjà la fenêtre
   binaire `annual_growth_period` ; #65 doit reprendre le *même* déclencheur de
   sénescence (entrée en dormance) quand il transforme la porte binaire en rampe.
3. **#63 — évitement d'ombre à l'initiation** · réduire l'**émission** de
   latéraux à l'ombre (pas seulement élaguer après — `shade_mortality` reste).
   Réutilise la machinerie de pondération de qualité (#3). Réagit au champ
   lumineux **corrigé par #62 (feuillus ; conifères via #7)**. Levier
   d'initiation bon marché ; compose avec #56.
4. **#64 — mémoire mécanique du bois** · bois de réaction / redressement /
   raidissement sous charge intégrés dans le temps (#10 dispo), au lieu d'un sag
   statique recalculé à chaque pas. Charge-driven, complément de #34 (âge-driven).

### Changement de moteur profond

5. **#56 — forme émergente : variante shadow-propagation (Palubicki 2009)** · 2ᵉ
   backend d'exposition (BHse reste le défaut) : la silhouette (cône conifère,
   fût clair) **émerge** de l'auto-ombrage + dominance apicale au lieu d'être
   prescrite par l'enveloppe `cone`. Compose avec #62 (lumière feuillus correcte)
   et #63 (levier d'initiation). Le plus profond du backlog ; tranche d'abord le
   compromis dirigeable-vs-émergent.

### Nouveaux modes orthogonaux (gros, n'altèrent pas le pipeline ligneux)

6. **#11 — croissance déterminée + fleurs + inflorescences** · bundle cohérent
   (un apex se **détermine** en fleur ; une inflorescence est un arbre de pousses
   déterminées). Lit le driver saisonnier (#65). Débloque forbs, fruits, et un
   2ᵉ déclencheur sympodial propre.
7. **#12 — tallage + méristèmes intercalaires (graminées)** · nouveau mode de
   croissance (zone basale, tallage depuis le collet) ; architecturalement
   orthogonal, aucun code ligneux à toucher.
8. **#44 — vignes / lianas** · obstacle comme **attracteur** (aujourd'hui
   purement répulsif) + thigmotropisme + état cherche/accroché. Réutilise
   `sim/obstacles.py`. Seulement si scènes de paysage avec structures.

### Piste parallèle — apparence (orthogonale à la forme)

9. **#53 — qualité infographique (épopée rendu/export glTF)** · normal maps →
    translucence feuille (`KHR_materials_diffuse_transmission`) → ORM → atlasing →
    LOD/instancing/vent. Matrice §12 de [`render-pipeline.md`](render-pipeline.md).
    Débloquée par rien, sous-tickets indépendants : à piquer dès qu'on veut une
    passe visuelle, en parallèle du travail de forme ci-dessus.

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
