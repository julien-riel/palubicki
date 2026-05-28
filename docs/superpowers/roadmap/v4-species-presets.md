# V4 — Presets d'espèces (reproduction Fig. 12)

**Statut** : Roadmap
**Préalable** : V3 (idéalement V2 minimum) pour disposer de tous les leviers.

## Objectif

Livrer un set de configurations YAML reproduisant qualitativement les espèces présentées en Figure 12 du papier Palubicki et al. 2009 :
- Pommier (apple)
- Chêne (oak)
- Frêne weeping (weeping ash)
- Conifère (pine/spruce)
- Saule pleureur
- Bouleau

## Travail attendu

Pour chaque espèce :
1. **Tuning paramétrique** : itérer manuellement (avec captures visuelles) sur enveloppe + tropismes + phyllotaxie + λ jusqu'à ressemblance.
2. **Texture bark** dédiée (chêne ≠ bouleau).
3. **Texture leaf** dédiée + forme.
4. **Preset YAML** complet dans `configs/species/<name>.yaml`.

CLI : `palubicki generate --species oak -o oak.glb` lit le preset, accepte des overrides.

## Risques

- Beaucoup d'aller-retour visuel — nécessite un workflow rapide de visualisation (gltf.report, Blender script, ou viewer custom).
- Certaines espèces du papier nécessitent des features non triviales (tropisme négatif fort pour le saule = plagiotropisme par poids). À vérifier que V1+V2+V3 suffisent.

## Hors scope

- Animation de croissance (timelapse).
- Variabilité réaliste intra-espèce automatisée (laisser à la combinatoire seed + petites perturbations).
