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

### Couplage feuille ↔ lumière (câblage sur #10 axe-temps + #14 feuilles)

1. **#62 — vraie surface de lame dans la grille LAI** · l'auto-ombrage lit
   aujourd'hui un `leaf_area` scalaire découplé du feuillage rendu ; injecter la
   surface réelle (morphologie déjà paramétrée, fonction d'aire partagée avec
   `geom/leaves.py`). **Prérequis de #63 et #56** : sans lui, toute réponse à
   l'ombre réagit à un signal faux et devra être re-tunée. Même principe de
   cohérence que #37 (appliqué aux feuilles, pas aux diamètres).

### Restaurer le filet conifère (#48 goldens tenus rouges)

2. **#55 — spray latéral cohérent (forme)** · référencer la plagiotropie **et**
   le repère radial d'insertion au plan de la branche-mère (au lieu du plan XY
   mondial) → éventail plat des conifères. Cadre structurel : à faire **avant**
   d'y poser les aiguilles. Candidat fort pour le correctif de forme de #48.
3. **#7 — fascicules d'aiguilles** · aiguilles de conifères (réparties le long du
   rameau, #36) regroupées en fascicules de 2–5, posées sur le cadre de spray
   corrigé par #55. Re-pin des goldens #48 une seule fois, avec #55.

### Driver saisonnier + réponses à l'ombre

4. **#65 — phénologie graduée** · remplacer l'interrupteur binaire
   `annual_growth_period` par une rampe (courbe `year_fraction` en MVP,
   degrés-jours en *nice-to-have*). Généralise la fenêtre de #10 ; **la floraison
   (#11) lira le même driver**, donc le poser avant d'empiler le saisonnier.
   **Coordonne avec #61 (livré)** : la caducité saisonnière lit déjà la fenêtre
   binaire `annual_growth_period` ; #65 doit reprendre le *même* déclencheur de
   sénescence (entrée en dormance) quand il transforme la porte binaire en rampe.
5. **#63 — évitement d'ombre à l'initiation** · réduire l'**émission** de
   latéraux à l'ombre (pas seulement élaguer après — `shade_mortality` reste).
   Réutilise la machinerie de pondération de qualité (#3). Réagit au champ
   lumineux **corrigé par #62**. Levier d'initiation bon marché ; compose avec #56.
6. **#64 — mémoire mécanique du bois** · bois de réaction / redressement /
   raidissement sous charge intégrés dans le temps (#10 dispo), au lieu d'un sag
   statique recalculé à chaque pas. Charge-driven, complément de #34 (âge-driven).

### Changement de moteur profond

7. **#56 — forme émergente : variante shadow-propagation (Palubicki 2009)** · 2ᵉ
   backend d'exposition (BHse reste le défaut) : la silhouette (cône conifère,
   fût clair) **émerge** de l'auto-ombrage + dominance apicale au lieu d'être
   prescrite par l'enveloppe `cone`. Compose avec #62 (lumière correcte) et #63
   (levier d'initiation). Le plus profond du backlog ; tranche d'abord le
   compromis dirigeable-vs-émergent.

### Nouveaux modes orthogonaux (gros, n'altèrent pas le pipeline ligneux)

8. **#11 — croissance déterminée + fleurs + inflorescences** · bundle cohérent
   (un apex se **détermine** en fleur ; une inflorescence est un arbre de pousses
   déterminées). Lit le driver saisonnier (#65). Débloque forbs, fruits, et un
   2ᵉ déclencheur sympodial propre.
9. **#12 — tallage + méristèmes intercalaires (graminées)** · nouveau mode de
   croissance (zone basale, tallage depuis le collet) ; architecturalement
   orthogonal, aucun code ligneux à toucher.
10. **#44 — vignes / lianas** · obstacle comme **attracteur** (aujourd'hui
    purement répulsif) + thigmotropisme + état cherche/accroché. Réutilise
    `sim/obstacles.py`. Seulement si scènes de paysage avec structures.

### Piste parallèle — apparence (orthogonale à la forme)

11. **#53 — qualité infographique (épopée rendu/export glTF)** · normal maps →
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
