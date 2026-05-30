# Sources botaniques & modélisation procédurale

Bibliographie des références qui sous-tendent le simulateur. Les primers
maison ([plant-structure.md](./plant-structure.md),
[simulator-gap-analysis.md](./simulator-gap-analysis.md)) sont des
vulgarisations — *ceci* est le matériau d'origine.

**Légende disponibilité :** 🟢 PDF libre · 🔴 derrière paywall (DOI / accès
institutionnel). Tout le canon « plantes procédurales » est hébergé en accès
libre par le labo de Prusinkiewicz : <https://algorithmicbotany.org/papers/>.

**Version machine :** ce document est le récit ; la version exploitable par le
code est [`src/palubicki/configs/literature.yaml`](../../src/palubicki/configs/literature.yaml).
Elle porte le bloc `sources:` (clé → citation/url/disponibilité) consommé par
`scripts/fetch_botany_sources.py` (téléchargement) et
`scripts/extract_botany_values.py` (extraction des valeurs), plus le bloc
`ranges:` (bornes ✓/✗ par espèce) que charge `sim.diagnostics.MetricRanges`. Les
deux peuvent diverger légèrement ; le `.md` reste la source narrative.

**Espèces (taxons nord-américains) :** les presets sont calibrés sur *Betula
papyrifera*, *Abies balsamea*, *Acer saccharum*, *Quercus rubra* et *Pinus
strobus* (mapping `species_latin:` dans `literature.yaml`), choisis pour matcher
les sources libres Silvics of North America et Wood Handbook. Les bornes
architecturales (`tree_height`/`crown_radius`/`trunk_base_diameter`) ciblent un
arbre **jeune (~30 ans)**, pas mature : le simulateur ne modélise pas 80+ ans.
Les bornes d'angles/phyllotaxie et de densité du bois sont indépendantes de
l'âge.

---

## 1. Le modèle implémenté

**Palubicki, W., Horel, K., Longay, S., Runions, A., Lane, B., Měch, R.,
Prusinkiewicz, P. (2009).** *Self-organizing tree models for image synthesis.*
ACM Transactions on Graphics 28(3), Art. 58 (SIGGRAPH 2009).
🟢 <https://algorithmicbotany.org/papers/selforg.sig2009.html>

> Le papier fondateur du projet. Le modèle **BHse** (markers dans une enveloppe
> → compétition des bourgeons → allocation Borchert-Honda → tropismes →
> shedding) que `src/palubicki/sim/` implémente. À lire en premier.

## 2. La bible — vocabulaire & L-systèmes

**Prusinkiewicz, P., Lindenmayer, A. (1990).** *The Algorithmic Beauty of
Plants (ABOP).* Springer-Verlag. Version électronique gratuite.
🟢 <https://algorithmicbotany.org/papers/abop/abop.pdf> (17 Mo) ·
version basse qualité 🟢 <https://algorithmicbotany.org/papers/abop/abop.lowquality.pdf> (4 Mo) ·
chapitres séparés : `abop/abop-ch[1-8].pdf`

> Référence de fond pour L-systèmes, phyllotaxie (angle d'or), tropismes,
> modèles de développement. Couvre le vocabulaire des primers.

## 3. Le flux de ressources « Borchert-Honda »

**Borchert, R., Honda, H. (1984).** *Control of development in the bifurcating
branch system of Tabebuia rosea: a computer simulation.* Botanical Gazette
145(2), 184–195.
🔴 DOI : <https://doi.org/10.1086/337443>

> Le mécanisme d'allocation racine→bourgeons de `src/palubicki/sim/bh.py`
> (paramètres `lambda_apical`, dominance apicale). Le « BH » de « BHse ».

## 4. Géométrie des angles de branchement

**Honda, H. (1971).** *Description of the form of trees by the parameters of
the tree-like body: Effects of the branching angle and the branch length on the
shape of the tree-like body.* Journal of Theoretical Biology 31(2), 331–338.
🔴 DOI : <https://doi.org/10.1016/0022-5193(71)90191-3>

> Formalise angle d'insertion + longueur de branche → forme globale. Sous-tend
> `phyllotaxy.branch_angle_by_order` et les tropismes plagiotropes.

## 5. Cousin algorithmique — colonisation de l'espace

**Runions, A., Lane, B., Prusinkiewicz, P. (2007).** *Modeling trees with a
space colonization algorithm.* Eurographics Workshop on Natural Phenomena 2007,
63–70.
🟢 <https://algorithmicbotany.org/papers/colonization.egwnp2007.html>

> Variante de la compétition pour l'espace par markers. Utile pour comprendre
> les alternatives au schéma BHse et le rôle des points d'attraction.

## 6. Lumière & environnement (V2/V3)

**Měch, R., Prusinkiewicz, P. (1996).** *Visual models of plants interacting
with their environment.* SIGGRAPH 1996, 397–410.
🟢 <https://algorithmicbotany.org/papers/enviro.sig96.html>

> Plantes réagissant à la lumière et aux obstacles — le cadre conceptuel
> derrière l'ombrage voxel (V2, `--light-enabled`) et la forêt + obstacles (V3).

---

## Comment télécharger

Les entrées 🟢 sont des PDF libres sur algorithmicbotany.org — soit en lien
direct (ABOP), soit via la page d'atterrissage qui pointe le PDF. Les entrées
🔴 (Honda 1971, Borchert & Honda 1984) sont dans des revues sous paywall :
résoudre le DOI donne la page éditeur (accès institutionnel ou achat).

Aucun de ces PDF n'est versionné dans le repo (binaires lourds) — ce document
est la **liste de liens** ; télécharger localement au besoin.
