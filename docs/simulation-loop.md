# Boucle de simulation — `sim/simulator.py`

Vue d'ensemble de `simulate_forest`, décomposée du plus général au plus
détaillé. Chaque section zoome sur une partie de la précédente.

---

## 1. Vue d'ensemble

Les trois grandes phases : construire la forêt, itérer année par année,
puis finaliser et exporter.

```mermaid
flowchart TD
    start([simulate_forest cfg]) --> build[build_forest<br/>arbres, marqueurs, obstacles]
    build --> grid[_init_light_grid<br/>grille voxels + obstacles]
    grid --> loop{{Boucle annuelle<br/>num_iterations}}
    loop -->|chaque itération| iter[_iteration_step]
    iter --> loop
    loop -->|saturation ou plus de bourgeons| final[Finalisation Phase 2D]
    final --> export[Forest → geom.builder → export.gltf .glb]
    export --> done([fin])
```

---

## 2. Une année : `_iteration_step`

Chaque itération choisit une branche selon le calendrier (`Clock`) et l'état
des bourgeons.

```mermaid
flowchart TD
    tick[t = iteration × dt] --> q{bourgeons<br/>actifs ?}
    q -->|non| brk([break])
    q -->|oui| season{saison de<br/>croissance ?}
    season -->|non — dormance| age[_apply_temporal_dynamics<br/>vieillissement seul, rien n'émerge]
    season -->|oui| perc[Phase Perception]
    perc --> grow[Phase Croissance]
    grow --> post[Post-pas]
    age --> next([itération suivante])
    post --> sat{2 itérations sans<br/>nouveau nœud ?}
    sat -->|oui| brk
    sat -->|non| next
```

---

## 3. Phase Perception

Calculée **une fois par itération**, sur l'union des bourgeons de tous les
arbres. Produit la `quality` par bourgeon qui pilotera la croissance.

```mermaid
flowchart TD
    L[light / light_perception<br/>_perceive_forest_light] --> Lout[light_factor + gradient par bourgeon]
    Lout --> S{shade_mortality<br/>activée ?}
    S -->|oui| K[shade_mortality.kill_shaded_buds<br/>bourgeons ombragés → DEAD]
    S -->|non| SP
    K --> SP[space_competition.perceive<br/>marqueurs dans le cône → qualité + direction]
    SP --> Q[_compute_quality<br/>qualité × light_factor × biais positionnel]
    Q --> Qout([quality par bourgeon])
```

> `_compute_quality` combine la qualité des marqueurs, le `light_factor` et le
> biais d'éclosion positionnel (`bud_break_bias` : acro / méso / basitone).

---

## 4. Phase Croissance — `_grow_tree`

Pour chaque arbre. Allocation Borchert-Honda du flux de vigueur, puis une
passe bourgeon-majeure qui émet **au plus un** internode par bourgeon.

```mermaid
flowchart TD
    sym{sympodial<br/>activé ?} -->|oui| promote[promote_lateral_if_failing<br/>latéral → terminal si l'axe stagne]
    sym -->|non| bh
    promote --> bh[bh.compute_v_subtree + allocate<br/>→ flux v_b par bourgeon]
    bh --> rec[shedding.record_qualities]
    rec --> perbud{{pour chaque<br/>bourgeon actif}}
    perbud --> decide[décision par bourgeon<br/>voir section 5]
    decide --> perbud
    perbud -->|fin| ret([nodes_created, new_positions])
```

---

## 5. Décision d'un bourgeon

Le cœur de la croissance : chaque bourgeon décide de rester dormant ou
d'émettre un nouveau nœud.

```mermaid
flowchart TD
    ema[recent_vigor = EMA v_b] --> vig{vigueur ≥<br/>seuil dormance ?}
    vig -->|non| dorm[state = DORMANT]
    vig -->|oui| dir[tropisms.growth_direction<br/>perception + ortho/gravi/photo + inertie]
    dir --> uturn{demi-tour ?<br/>cos < cos_min}
    uturn -->|oui| dorm
    uturn -->|non| obst{obstacle ?}
    obst -->|segment bloqué| dorm
    obst -->|point contenu| dead[state = DEAD]
    obst -->|libre| emit[_emit_node]
    emit --> phyl[phyllotaxy<br/>Node + Internode + buds + feuilles]
    phyl --> kill[bourgeon courant → DEAD]
```

> `_emit_node` crée le `Node`, l'`Internode` (avec `vigor = v_b`), le bourgeon
> terminal, les latéraux, les bourgeons de réserve, et les feuilles
> (azimuts phyllotaxiques). Le bourgeon courant devient `DEAD`.

---

## 6. Post-pas et finalisation

```mermaid
flowchart TD
    subgraph post [Post-pas — chaque itération de croissance]
        m[markers.kill_near<br/>espace colonisé consommé] --> sh[shedding.shed_low_quality<br/>abscission + réitération des réserves]
        sh --> td[_apply_temporal_dynamics]
    end
    td --> order[ordre strict :<br/>élongation → diamètres pipe → sag]

    subgraph fin [Finalisation Phase 2D — après la boucle]
        snap[length = length_target] --> diam[update_diameters_incremental<br/>pipe model]
        diam --> sag[apply_sag<br/>ploiement final]
    end

    order -.-> snap
```

> **Ordre imposé** dans `_apply_temporal_dynamics` : longueurs d'abord (le sag
> lit la charge `longueur × diamètre²`), puis diamètres (le sag lit le
> diamètre), puis sag en dernier.
