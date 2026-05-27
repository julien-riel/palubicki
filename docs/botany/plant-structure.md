# Plant Structure & Appearance: A Developer's Reference

*A science-based primer on plant morphology for engineers building 3D plant models. The goal is to give you a vocabulary and a mental model that maps cleanly onto data structures, so you can read botany papers and translate them into code.*

---

## 1. Why botany maps so well to data structures

Plants are, structurally, one of the most computer-science-friendly subjects in biology. Three properties make this true:

1. **Modularity.** A plant is built by repeating a small handful of unit parts (the *phytomer*) over and over. This is composition, not invention.
2. **Recursion.** Each branch is, with minor parameter changes, "another tree." Self-similarity is everywhere — leaf venation, branching patterns, root systems.
3. **Local rules, global form.** A plant has no central planner. Each meristem (growth point) follows local rules; the global shape *emerges*. This is exactly what rewriting systems (L-systems), agent simulations, and procedural generation do.

Because of this, the same handful of data structures show up again and again when you model plants:

| Botanical concept | Natural data structure |
|---|---|
| Branch hierarchy | Rooted tree (parent → children) |
| Internodes between buds | Edge with length / radius attributes |
| Bud / meristem | Node with state (active, dormant, aborted) |
| Phyllotaxis | Angle parameter on each node |
| Growth over seasons | Time-indexed sequence of tree snapshots |
| Symmetry / repetition | L-system production rules (grammar) |
| Vasculature / "pipes" | Allometric weights propagated up the tree |

The rest of this document is the botanical vocabulary you need to populate those structures correctly.

---

## 2. The modular body plan: the phytomer

The fundamental repeating unit of a vascular plant shoot is the **phytomer** (sometimes *metamer*). One phytomer consists of:

- a **node** (the point where a leaf attaches),
- one **internode** (the stem segment below the node),
- one or more **leaves** at the node,
- one or more **axillary buds** in the axils of those leaves (the angle between leaf and stem).

A shoot is, structurally, a stack of phytomers produced by an apical meristem at the tip.

```text
       leaf
        \
   ──────●─── ← node + axillary bud
         │
         │   ← internode
   ──────●───
         │
         │
   ──────●───
         │       (older phytomers below)
```

As a record:

```pseudo
struct Phytomer:
    internode_length: float
    internode_radius: float
    leaves:         List<Leaf>          # usually 1, 2, or 3 per node
    axillary_buds:  List<Bud>           # one per leaf, typically
    node_position:  Vec3                # derived from parent + length + angles
    orientation:    Quaternion          # the "turtle state" after this phytomer
```

Every branch in any vascular plant — grass blade, oak twig, rose stem — is a chain of phytomers. Differences between species are differences in (a) phytomer parameters and (b) the rules by which buds activate.

---

## 3. Meristems: the engines of growth

A **meristem** is a region of undifferentiated, actively-dividing cells. Plants grow only at meristems — not uniformly along the whole body. There are four types you must model:

### 3.1 Apical meristem (SAM at shoot tips, RAM at root tips)
Adds new phytomers at the tip of a shoot or root. Determines **primary growth** (elongation). In your model, this is the "turtle" that pushes new segments forward.

### 3.2 Axillary (lateral) meristems
Sit in leaf axils as dormant buds. When released from dormancy they become **new branches** — each one is a fresh apical meristem. This is the *fork* in your tree data structure.

### 3.3 Intercalary meristems
Sit at the **base** of internodes or leaves rather than at the tip. **Grasses use these**: that is why a lawn keeps growing after mowing — you remove the tip, but the growing zone is at the base. This single fact dictates how you have to model grass differently from a tree.

### 3.4 Lateral meristems (vascular cambium, cork cambium)
Sit as cylindrical sheaths inside woody stems. They cause **secondary growth**: thickening, bark, wood, annual rings. Only gymnosperms and most dicotyledonous trees and shrubs have these. Monocots (grasses, palms, lilies) generally do not, which is why a palm trunk does not get thicker the way an oak does.

### 3.5 Determinate vs. indeterminate growth

- **Indeterminate**: the apical meristem keeps producing phytomers indefinitely (most trees and vines).
- **Determinate**: the apical meristem terminates in a fixed structure — usually a flower or inflorescence — and stops. After termination, further growth must come from axillary meristems (a *sympodial* pattern).

This distinction drives branching architecture (see §4.1).

---

## 4. Branching architecture

### 4.1 Monopodial vs. sympodial

This is the single most important distinction in branching:

- **Monopodial**: one persistent apical meristem produces the main axis year after year. The trunk is one continuous lineage of phytomers. *Examples: most conifers (spruce, fir), young pines.*

- **Sympodial**: the apical meristem terminates (flowers, aborts, or is shed) every cycle. The "main axis" is then a relay made of successive axillary branches each taking over. *Examples: lilac, elm, many tropical trees, basil after flowering.*

The two patterns produce visibly different trees: monopodial = straight central leader (a Christmas-tree silhouette); sympodial = forked, no single trunk continuing to the top.

```pseudo
# Monopodial: parent axis keeps growing
Axis = sequence of Phytomers produced by the same SAM
       + children (lateral branches, lower order)

# Sympodial: each axis terminates; the "trunk" is a chain of axes
Trunk = [Axis_1, Axis_2, Axis_3, ...]
        where each Axis_k+1 is an axillary branch from Axis_k's terminal region
```

### 4.2 Apical dominance

The active apical meristem releases auxin downward, which **suppresses** axillary buds nearby. Effects:

- Strong apical dominance → tall, narrow, weakly-branched form (firs, young pines).
- Weak apical dominance → bushy, widely-branched form (apple, willow).
- Cut the tip → release buds below → "bushing" response (the basis of pruning).

In a procedural model, this is naturally expressed as: *a bud's probability of activating depends on its distance from the active tip and on its position in the hierarchy.*

### 4.3 Acrotony, mesotony, basitony

When axillary buds *do* break, **which** ones break? Three patterns:

- **Acrotonic**: buds closest to the apex are favored. Typical of trees — produces the classic excurrent crown.
- **Mesotonic**: middle buds favored.
- **Basitonic**: buds near the base are favored. Typical of shrubs and suckering plants — produces multi-stemmed clumps.

### 4.4 Plagiotropy vs. orthotropy

- **Orthotropic axes** grow vertically, are radially symmetric, often produce more orthotropic branches. The trunk.
- **Plagiotropic axes** grow horizontally or obliquely, often have bilateral leaf arrangement (flat plane of leaves), and produce only short-lived lateral branches. Most "side branches" of a fir are plagiotropic.

A single plant can mix the two: the main axis is orthotropic; lateral branches are plagiotropic. This is why pine branches are flat sprays while the trunk is a pole.

### 4.5 The Hallé–Oldeman architectural models

In the 1970s, Francis Hallé, Roelof Oldeman, and P.B. Tomlinson catalogued the world's trees into **23 architectural models** based on:
- monopodial vs. sympodial,
- orthotropic vs. plagiotropic axes,
- determinate vs. indeterminate growth,
- position of reproductive structures,
- rhythmic vs. continuous growth.

Examples worth knowing by name:

| Model | Pattern | Examples |
|---|---|---|
| **Rauh** | Monopodial trunk + rhythmic branches, lateral and terminal flowering | Pines, oaks, many temperate trees |
| **Massart** | Monopodial trunk, plagiotropic tiered branches | Norfolk pine, *Araucaria*, young firs |
| **Leeuwenberg** | Sympodial; each axis ends in a flower; equal forking | Manihot, oleander |
| **Troll** | All axes plagiotropic; trunk built by successive bending of branches | Many tropical legumes |
| **Corner** | Single unbranched stem ending in inflorescence | Palms, papayas |

You don't need to implement all 23, but the model gives you a checklist of independent axes along which species vary.

---

## 5. Phyllotaxis: leaf and bud arrangement

Phyllotaxis describes the geometric pattern in which leaves (and therefore axillary buds, and therefore branches) are placed around the stem. There are four canonical patterns:

| Pattern | Angle between successive leaves | Examples |
|---|---|---|
| **Distichous** (alternate, 2-ranked) | 180° | Grasses, irises |
| **Opposite** (decussate) | Pairs at 180°, successive pairs rotated 90° | Maples, mints |
| **Whorled** | n leaves per node, 360/n apart, whorls rotated | *Galium*, oleander |
| **Spiral** | ~137.5° (the **golden angle**) | Most dicots, conifers |

### The golden angle

Spiral phyllotaxis converges on a divergence angle of **≈ 137.507°** (360° × (1 − 1/φ), with φ the golden ratio). This is not mystical — it's the angle that minimizes overlap of leaves seen from above, maximizing light capture. Numerically, successive leaves never align because φ is irrational.

In code:

```pseudo
GOLDEN_ANGLE = 137.50776   # degrees
for i in 0 .. n_leaves:
    azimuth = (i * GOLDEN_ANGLE) mod 360
    height  = i * internode_length
    place_leaf(azimuth, height)
```

The visible spirals you can count on a pinecone, sunflower head, or pineapple (parastichies) are consecutive **Fibonacci numbers** (5/8, 8/13, 13/21…) — a direct consequence of the irrationality of φ.

### Why this matters for branching, not just leaves

Every axillary bud sits in a leaf axil. The phyllotaxis of leaves *is* the phyllotaxis of potential branches. A maple's branching looks "crossed" (opposite-decussate); a pine's looks helical (spiral). Get phyllotaxis wrong and the whole tree silhouette is wrong.

---

## 6. Leaves

### 6.1 Anatomy

A typical leaf has:

- **Blade (lamina)** — the flat photosynthetic surface.
- **Petiole** — the stalk attaching blade to stem. May be absent (sessile leaf).
- **Stipules** — small appendages at the petiole base; often shed early.
- **Midrib + venation** — the vascular skeleton.

```pseudo
struct Leaf:
    petiole_length: float
    blade_length:   float
    blade_width:    float
    shape:          enum {lanceolate, ovate, elliptic, cordate, linear, ...}
    margin:         enum {entire, serrate, dentate, lobed, ...}
    venation:       enum {parallel, pinnate, palmate, dichotomous}
    insertion_angle: float          # angle off the stem
    rotation:       float           # twist about petiole axis
```

### 6.2 Simple vs. compound

- **Simple leaf**: one undivided blade.
- **Compound leaf**: the blade is divided into separate **leaflets**, each looking like a small leaf.
  - **Pinnately compound**: leaflets along a central rachis (ash, walnut, rose).
  - **Palmately compound**: leaflets radiating from one point (horse chestnut, marijuana, lupine).
  - **Bipinnate / tripinnate**: rachis itself is branched (mimosa, carrot family).

A compound leaf is itself a small tree structure — a rachis with phytomer-like nodes bearing leaflets and an apical leaflet. You can recurse the same data structure.

**Recognition trick**: a compound leaf has a bud at the base of the *whole leaf*, never at the base of a leaflet. That tells you what is one leaf vs. a stem with simple leaves.

### 6.3 Venation

- **Parallel** — monocots (grasses, lilies). Veins run along the blade.
- **Pinnate** (feather-like) — one midrib with branching laterals (oak, beech).
- **Palmate** (hand-like) — several main veins from the base (maple, grape).
- **Dichotomous** — equal forking (ginkgo).

Venation maps to a 2D graph embedded on the blade surface; for 3D rendering it influences how the leaf bends, ages, and reflects light.

### 6.4 Margin, shape, apex, base

These are catalogued in **leaf-shape glossaries** (Hickey 1973 is the standard) with dozens of named forms — linear, lanceolate, ovate, obovate, cordate, reniform, deltoid, etc. For most procedural pipelines, a parametric blade with controllable length:width ratio, base curvature, apex angle, and margin function (sinusoidal teeth, lobes, etc.) covers 90% of species.

### 6.5 Leaf life span

- **Deciduous** — shed in one season (most temperate broadleaf trees, larch among conifers).
- **Evergreen** — retained 2–10+ years (most conifers, holly, magnolia).
- **Marcescent** — dead but retained on the tree through winter (young beech, oak).

Deciduousness drives seasonal appearance and is independent of conifer/broadleaf status (larch is a deciduous conifer; live oak is an evergreen broadleaf).

---

## 7. Roots

Roots mirror shoots topologically but with different rules. There are two basic systems:

- **Taproot system**: one dominant primary root, smaller laterals branching from it. Typical of dicots, conifers. Carrots, oaks.
- **Fibrous (diffuse) root system**: many roots of similar size, no dominant axis. Typical of monocots. Grasses, palms.

Roots branch *endogenously* (from inside the pericycle layer) rather than from axillary buds in a regular phyllotactic pattern. So root branching is irregular and adaptive — it tracks water and nutrient gradients. Computational root models (e.g., **RootBox**, **ArchiSimple**) typically use stochastic branching with a density that depends on local soil properties.

For above-ground visual modeling, roots usually matter only at the surface flare (root collar / buttresses) and as exposed prop roots in some species.

---

## 8. Stems and secondary growth

### 8.1 Primary growth
Elongation at the tip from the apical meristem. Adds new phytomers. Diameter at this stage is set by the apical meristem's size.

### 8.2 Secondary growth (woody plants only)
The **vascular cambium** is a cylinder of dividing cells just inside the bark. It adds:
- **Xylem (wood)** inward,
- **Phloem** outward.

This is what makes a tree's trunk thicker over time. Each year's xylem forms a visible **annual ring** in temperate climates (wide early-season "earlywood", dense late-season "latewood"). Tropical trees may lack distinct rings.

A second meristem, the **cork cambium**, produces **bark** outward. As the trunk expands, bark cracks in species-specific patterns: smooth (beech, young birch), plates (pine), fissured (oak), shaggy (shagbark hickory), peeling sheets (paper birch, eucalyptus).

### 8.3 The pipe model (Shinozaki et al. 1964)

A useful first-order rule for stem diameter:

> The cross-sectional area of a stem at any point is proportional to the total leaf area it supports above that point.

Equivalently, the trunk is a "bundle of pipes" each leading to one unit of leaf. This implies the **da Vinci rule**: the sum of cross-sectional areas of child branches equals the cross-sectional area of the parent.

```pseudo
# Approximate; exponent typically 2.0–2.5
radius(parent)^n = sum(radius(child)^n for child in children)
```

This single equation generates believable trunk taper from a branching topology alone.

### 8.4 Bark texture

Bark patterns emerge from the interaction between expansion of the trunk and the rigidity / shedding behavior of the cork layer. For appearance modeling these are usually procedural textures driven by species-specific parameters (crack frequency, plate aspect ratio, color, lichen overlay).

---

## 9. Reproductive structures

### 9.1 Flowers (angiosperms)

A flower is, developmentally, a determinate shoot whose phytomers bear specialized organs instead of ordinary leaves. From the outside in, four whorls:

1. **Calyx** — sepals (usually green, protective).
2. **Corolla** — petals (usually showy).
3. **Androecium** — stamens (male; anther + filament).
4. **Gynoecium** — carpels / pistils (female; stigma, style, ovary).

A compact notation, the **floral formula**:

```text
K5 C5 A∞ G(5)
↑   ↑  ↑   ↑
sepals petals stamens carpels (fused, indicated by parentheses)
```

Symmetry:

- **Actinomorphic** (radial) — many planes of symmetry. *Lily, rose, apple.*
- **Zygomorphic** (bilateral) — one plane. *Orchid, pea, snapdragon.*

For 3D modeling, a flower is a short determinate shoot with a fixed phyllotaxis (often whorled) and parametric organ shapes. Many flowers can be generated as a small L-system or as a parameterized swept profile.

### 9.2 Inflorescences

Flowers are rarely solitary; they are grouped in **inflorescences**, which are themselves tree structures with their own architectural types:

| Type | Shape | Examples |
|---|---|---|
| **Raceme** | Unbranched axis, stalked flowers along it | Lupine, foxglove |
| **Spike** | Unbranched axis, sessile flowers | Plantain, mullein |
| **Panicle** | Branched raceme | Oat, lilac |
| **Umbel** | All pedicels from a single point | Carrot family, onion |
| **Corymb** | Flat-topped raceme (lower pedicels longer) | Yarrow |
| **Cyme** | Determinate; central flower opens first | Forget-me-not, elder |
| **Capitulum (head)** | Many sessile flowers on a flattened receptacle | Sunflower, daisy |

Capitula are particularly important visually — a sunflower head is a parastichy lattice of hundreds of disk florets arranged by the golden angle.

### 9.3 Cones (gymnosperms)

Conifers, ginkgos, cycads, and gnetophytes are **gymnosperms** — "naked seeds", carried on cone scales rather than enclosed in an ovary. A pine cone, structurally, is a determinate shoot whose phytomers bear cone scales in spiral phyllotaxis. Same golden-angle math as a sunflower; same parastichy counts.

Conifers carry:
- **Pollen cones** (small, soft, short-lived) — male.
- **Seed cones** (larger, woody when mature) — female.

### 9.4 Fruits

A fruit is a matured ovary (sometimes with accessory tissue). The main classes:

- **Simple fruit** — one ovary of one flower.
  - *Fleshy*: berry (tomato, grape), drupe (cherry, peach — single stony pit), pome (apple, pear — accessory tissue is the floral tube).
  - *Dry, dehiscent*: capsule (poppy), legume (pea), follicle (milkweed).
  - *Dry, indehiscent*: nut (acorn), achene (sunflower seed), samara (maple key), caryopsis (grain).
- **Aggregate fruit** — many ovaries from one flower (raspberry, magnolia).
- **Multiple fruit** — many ovaries from many flowers fused together (pineapple, mulberry, fig).

For visual modeling: shape, surface (smooth, hairy, warty, scaly), color trajectory through ripening, attachment (pedicel length and angle), and clustering pattern (single, paired, raceme, panicle).

---

## 10. Plant groups and their structural signatures

These are the broad categories worth distinguishing for procedural generation. They differ in *which subset of the above mechanisms* they use.

### 10.1 Grasses (Poaceae) and other graminoids

- **Monocots**, parallel venation, fibrous root system.
- **Intercalary meristem** at the base of each leaf and internode — growth continues after grazing/mowing.
- **Tillering**: new shoots arise from basal buds rather than from upper axils. Form is a clump.
- Distichous leaves (two-ranked).
- Flowers reduced and wind-pollinated; inflorescence is a spike or panicle of **spikelets**.
- No secondary growth — stems do not thicken with age.
- Often have hollow internodes ("culms") with solid nodes.

**Model implication**: a grass plant is a *cluster* of independent shoots ("tillers") sharing a base, each shoot a short linear chain of leaves, each leaf elongating from its base. Very different topology from a tree.

### 10.2 Herbaceous forbs (non-grass herbs)

- Mostly **dicots**: pinnate/palmate venation, often a taproot.
- No (or minimal) secondary growth — stays soft, dies back yearly.
- Wide variety of leaf arrangements (alternate, opposite, basal rosette).
- Many are determinate: rosette → bolt → terminal inflorescence → die.

Examples: dandelion, daisy, sunflower, mint, plantain.

### 10.3 Shrubs

- Woody but multi-stemmed from the base. No single trunk.
- Basitonic branching dominates.
- Secondary growth present but limited in extent.

Examples: lilac, dogwood, blueberry, rhododendron.

### 10.4 Deciduous broadleaf trees (woody angiosperms)

- Single dominant trunk (in forest-grown form) with strong secondary growth.
- Broad leaves with reticulate (pinnate/palmate) venation.
- Wide range of architectural models: Rauh (oak, ash), Troll (legumes), Leeuwenberg (some maples after pollarding).
- Decurrent crown common: as the tree ages, apical dominance weakens, multiple co-dominant branches form a spreading canopy.
- Annual leaf drop in temperate species; seasonal silhouette varies dramatically (full leaf, autumn color, bare, bud break).

Examples: oak, maple, beech, birch, ash, elm.

### 10.5 Conifers (woody gymnosperms)

- Strong apical dominance → **excurrent** crown (single straight central leader, narrow conical or columnar form, especially when young).
- Often Massart or Rauh architectural model.
- Leaves: **needles** (pines, spruces, firs), **scales** (cypresses, junipers, cedars), or flat needle-like (yew, hemlock).
- Needles often clustered: in **fascicles** of 2–5 in pines, single on short shoots in larches and cedars.
- Whorled lateral branches in many species (true firs, spruces) — gives the tiered "Christmas tree" silhouette.
- Reproductive structures are cones (see §9.3), not flowers.
- Most are evergreen (larch and bald cypress are notable deciduous exceptions).

Examples: pine, spruce, fir, cedar, hemlock, larch, cypress, juniper, yew, sequoia.

### 10.6 Vines and lianas

- Long, slender stems that cannot support themselves; rely on external supports.
- Climbing mechanisms:
  - **Twining** stems (morning glory, beans) — the whole stem winds.
  - **Tendrils** (grape, pea) — modified leaves or stems that coil on contact.
  - **Adhesive pads or aerial roots** (Boston ivy, English ivy).
  - **Hooks or scrambling** (rose, *Rubus*).
- Often have long internodes between leaves while searching for a support, then short ones once established.

### 10.7 Bulbs, corms, rosettes, succulents — non-canonical forms

- **Bulbs** (onion, tulip): the "stem" is a compressed plate; the "bulb" is layered leaf bases storing food.
- **Rosettes** (dandelion, agave): leaves with zero internode length, all clustered at ground level.
- **Succulents** (cacti, *Euphorbia*): leaves reduced to spines (cacti) or absent; stem itself is photosynthetic and water-storing.

These are still made of phytomers — just with extreme parameter values (internode length → 0, leaf form → spine, stem geometry → cylinder/sphere).

---

## 11. Quantitative patterns: numbers you can hard-code

### 11.1 Allometric scaling

Many plant dimensions are linked by power-law relationships:

- **Trunk diameter vs. height**: usually `H ∝ D^(2/3)` (mechanical-buckling limit, McMahon 1973). Tall trees have disproportionately thick trunks.
- **Pipe model**: branch cross-sectional area ∝ leaf area supported (see §8.3).
- **Leaf mass vs. leaf area**: roughly proportional within a species; varies systematically across species (the Leaf Economics Spectrum, Wright et al. 2004).
- **Root vs. shoot biomass**: roughly 1:4 to 1:1 depending on species and conditions.

### 11.2 Self-similarity and fractal dimension

Tree crowns measured in the field have fractal dimensions typically in the range **2.0–2.7** (3 would mean filling space completely). This is a single tunable parameter for "how dense does the crown feel."

### 11.3 Branching order analysis (Strahler / Horton)

Borrowed from hydrology and applied to branch topology:

- **Strahler order**: a terminal twig is order 1; where two order-N branches meet, the parent is order N+1; where an order-N meets a lower order, the parent stays N.
- The ratio of branches of order N to branches of order N+1 (the **bifurcation ratio**) is typically **3 to 5** for trees, similar to river networks.

These ratios are useful both for generating plausible trees and for validating ones you've generated.

### 11.4 Divergence angles

| Pattern | Angle |
|---|---|
| Spiral (Fibonacci) | 137.508° |
| Opposite-decussate | 90° between successive pairs |
| Distichous | 180° |
| Whorled (n leaves) | 360°/n, offset between whorls |

### 11.5 Insertion angle of branches

Typically **30°–60°** off the parent axis. Often varies systematically with branch order (lower orders steeper, higher orders flatter) and species. Many species also show **plagiotropic re-orientation**: a branch starts at one angle, then bends toward horizontal over time as gravity wins against gravitropism.

---

## 12. Modeling frameworks worth knowing

### 12.1 L-systems (Lindenmayer, 1968)

A **rewriting grammar** where each symbol represents a plant organ (or turtle command) and production rules replace each symbol with a string of symbols at every time step. Adding context-sensitivity, stochasticity, parameters, and differential equations gives **L+C-systems** capable of representing real plants.

Trivial example (a binary branching tree):

```text
axiom:  A
rule:   A → F[+A][-A]F A
```

After three rewrites: `F[+F[+A][-A]FA][-F[+A][-A]FA]FF[+A][-A]FA`. Run a turtle interpreter (`F` = forward, `+`/`-` = rotate, `[`/`]` = push/pop state) on this string and you get a branching figure.

Implementations: **L-Py** (Python, INRIA), **GroIMP** (Java).

**Strength**: extremely compact for self-similar structures; matches the biological "local rules" intuition perfectly.
**Weakness**: hard to add global constraints (light competition, mechanical loading) without extensions.

### 12.2 Tree-graph / object-oriented models

Represent the plant as an explicit tree of phytomer objects with parent-child links and attribute dictionaries. Iterate growth as a function applied to nodes.

```pseudo
class Bud:
    state:          enum {dormant, active, aborted, flowered}
    age:            int
    apical:         bool
    next_step(env): produces new Phytomer or transitions state

class Phytomer:
    parent:         Phytomer | None
    children:       List[Phytomer]
    leaves:         List[Leaf]
    buds:           List[Bud]
    length, radius, orientation, age, ...
```

**Strength**: easy to query, edit, attach physics, render, persist.
**Weakness**: more code, less concise than L-systems.

### 12.3 Functional-Structural Plant Models (FSPM)

The state of the art in scientific plant modeling. An FSPM combines:
- a **structural** model (the tree of phytomers, as above),
- with **functional** models attached at each organ: photosynthesis, water transport, sugar allocation (source-sink), mechanical loading, light interception (often via ray-tracing or radiosity).

Major systems: **OpenAlea** (Python ecosystem from INRIA), **GroIMP** (Java, with the XL language), the older **AMAPsim** lineage.

Reference papers: Vos et al. 2010 ("Functional–structural plant modelling: a new versatile tool in crop science"); Godin & Sinoquet 2005.

### 12.4 Procedural / artistic models

For pure visualization (games, films), purely procedural systems trade biological fidelity for art-directability:
- **Weber & Penn 1995** ("Creation and Rendering of Realistic Trees") — the model behind Blender's **Sapling Tree Generator** and SpeedTree.
- **Space colonization algorithm** (Runions et al. 2007) — branches grow toward attractor points in space. Simple, gives organic-looking trees in a few hundred lines of code.

These are scientifically lighter but understand the same vocabulary (apical dominance, branching angle, phyllotaxis) — they just expose it as artist sliders rather than physiological state.

---

## 13. A minimal vocabulary checklist

If you can confidently define each of these, you can read a botanical morphology paper and translate it into a data structure:

- phytomer, node, internode, axil, bract
- apical meristem, axillary meristem, intercalary meristem, cambium
- monopodial, sympodial, determinate, indeterminate
- apical dominance, acrotony, basitony
- orthotropic, plagiotropic
- phyllotaxis: distichous, opposite-decussate, whorled, spiral; divergence angle
- simple vs. compound leaf; pinnate, palmate, bipinnate
- venation: parallel, pinnate, palmate
- primary vs. secondary growth; xylem, phloem, bark
- pipe model, allometry, da Vinci rule
- calyx, corolla, androecium, gynoecium; actinomorphic, zygomorphic
- raceme, spike, panicle, umbel, corymb, cyme, capitulum
- berry, drupe, pome, capsule, achene, samara
- monocot vs. dicot; angiosperm vs. gymnosperm
- L-system, FSPM

---

## 14. References for further reading

**Textbooks**
- Raven, P.H., Evert, R.F., Eichhorn, S.E. *Biology of Plants*. (The standard undergraduate plant-biology text.)
- Bell, A.D. *Plant Form: An Illustrated Guide to Flowering Plant Morphology*. Oxford UP. — Indispensable visual reference; written with computational morphologists in mind.
- Mauseth, J.D. *Botany: An Introduction to Plant Biology*.

**Architecture and form**
- Hallé, F., Oldeman, R.A.A., Tomlinson, P.B. *Tropical Trees and Forests: An Architectural Analysis*. Springer, 1978. — The 23 architectural models.
- Barthélémy, D. & Caraglio, Y. (2007) "Plant Architecture: A Dynamic, Multilevel and Comprehensive Approach to Plant Form, Structure and Ontogeny." *Annals of Botany* 99: 375–407.

**Modeling**
- Prusinkiewicz, P. & Lindenmayer, A. *The Algorithmic Beauty of Plants*. Springer, 1990. Free PDF at algorithmicbotany.org. — The L-system bible; should be on every plant-graphics developer's desk.
- Prusinkiewicz, P. (2004) "Modeling plant growth and development." *Current Opinion in Plant Biology* 7: 79–83.
- Vos, J. et al. (2010) "Functional–structural plant modelling: a new versatile tool in crop science." *Journal of Experimental Botany* 61: 2101–2115.
- Godin, C. & Sinoquet, H. (2005) "Functional–structural plant modelling." *New Phytologist* 166: 705–708.
- Weber, J. & Penn, J. (1995) "Creation and rendering of realistic trees." *SIGGRAPH '95*.
- Runions, A., Lane, B., Prusinkiewicz, P. (2007) "Modeling Trees with a Space Colonization Algorithm." *Eurographics Workshop on Natural Phenomena*.

**Allometry and scaling**
- Shinozaki, K. et al. (1964) "A quantitative analysis of plant form — the pipe model theory." *Japanese Journal of Ecology* 14: 97–105, 133–139.
- McMahon, T.A. (1973) "Size and shape in biology." *Science* 179: 1201–1204.
- Niklas, K.J. *Plant Allometry: The Scaling of Form and Process*. University of Chicago Press, 1994.

**Leaf form**
- Hickey, L.J. (1973) "Classification of the architecture of dicotyledonous leaves." *American Journal of Botany* 60: 17–33.
- Wright, I.J. et al. (2004) "The worldwide leaf economics spectrum." *Nature* 428: 821–827.

**Open-source software**
- *OpenAlea* — https://openalea.rtfd.io — Python framework for FSPMs.
- *L-Py* — L-systems in Python, part of OpenAlea.
- *GroIMP* — Java/XL platform for relational growth grammars.
- *Blender Sapling* add-on — Weber–Penn implementation, good for quick artistic trees.
