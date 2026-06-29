# 0019. Multi-config sweep: sample independent palette/font style-configs into separate datasets

- Status: Accepted
- Date: 2026-06-29

## Context

Phase 1 ([ADR-0018](0018-generator-structure-recipe-registry.md), PR #10) gave label-neutral variety *within one fixed
global style*: a single canonical palette and a single font. The `palette-compliance` and `font-compliance` rules are
judged against that one house style, so a checker could still pass them by memorizing "the Charr palette / font is the
compliant one." That is an absolute-style prior - exactly the memorization risk [ADR-0018](0018-generator-structure-recipe-registry.md)
set out to remove, but could not for these two rules. The reason is structural: palette and font are label-bearing only
*relative to a declared expectation*, and a dataset declares exactly one palette and one font-set (in its `charr.toml`).
Raising palette/font variety is Phase 2 of [issue #7](https://github.com/mvherweg/charr/issues/7).

You cannot randomize palette/font *within* a dataset - that would leave no single declared expectation to judge against,
making both rules meaningless. The variety has to come from sweeping across *multiple* datasets, each internally
consistent, unioned at eval. `charr-eval` already accepts multiple manifests and discovers each one's `charr.toml`
([ADR-0010](0010-three-packages-eval-drives-charr.md), [ADR-0011](0011-dataset-manifest-as-unit.md)), so the eval side
needs no change.

Forces:

- **A linter judges against declared rules, not taste.** Any approved colour set must be able to co-occur with any
  approved font set; there is no reason a given palette implies a given font. Curating coherent "house style" bundles
  would model a reviewer-with-taste, not a rule-checker. Fonts are themselves a palette: more than one font may be
  approved for a dataset (we cap the approved set at three).
- **Total role-rotation is the prize.** If palettes and font-sets are sampled *independently per config*, a concrete
  colour is in-palette in one dataset and a violation in another, and serif is the approved family in one dataset and a
  violation in another. Compliance becomes judgeable only relative to the declared config, so there is no absolute style
  left to memorize - the strongest possible anti-prior, and it falls straight out of independent sampling.
- **Ground truth stays by construction** ([ADR-0015](0015-ground-truth-by-construction.md)). A config's palette and
  font-set are fixed and written to its `charr.toml`; a compliant chart draws only from them, and the single intended
  violation draws from outside them. Nothing is re-derived from pixels.
- **Coverage must stay strong.** If a config could declare an *empty* palette ("anything goes"), `palette-compliance`
  would be unservable there and per-config coverage would weaken to a mere union property. We avoid that by sampling
  non-empty sets (palette of 3-6 colours, 1-3 fonts), so every config still covers all 20 cells. The separate concern -
  a real user who enables the rules but configures no palette - is a checker-robustness matter, handled deterministically
  in `charr` ([issue #14](https://github.com/mvherweg/charr/issues/14)), not a generator variety knob.

## Decision

**We will generate across N independently-sampled style-configs - each a palette and an approved-font set - writing one
self-describing dataset per config and unioning them at eval.**

- **A style-config is sampled, not curated.** Per config: a palette of K colours (K in 3..6 - the floor of three lets a
  pie's slices and a multi-group chart's series each take a distinct palette colour) and an approved-font set of F
  families (F in 1..3), drawn independently and seeded from the base seed. The concrete sampling mechanics - the colour
  space and the minimum pairwise distance that makes palette and off-palette colours unambiguous - are
  [ADR-0020](0020-colour-sampling-ciede2000.md); the curated mutually distinct supported font set and bundling fonts
  in-repo are [ADR-0021](0021-bundled-fonts-and-delivery.md). This ADR fixes only the *shape*: independent,
  combinatorial, non-empty, seeded.
- **Independent and combinatorial, no bundles.** Palette and font-set are sampled independently, so any palette can
  co-occur with any font-set. We do not curate coherent house styles.
- **One dataset per config.** A run writes `out_dir/config-00/`, `config-01/`, ..., each a complete dataset unit
  ([ADR-0011](0011-dataset-manifest-as-unit.md)): `images/`, `labels.jsonl`, a `charr.toml` carrying *that config's*
  palette and fonts, and a `meta.json` recording the concrete sampled palette/fonts and seed. `charr-eval out_dir/*/labels.jsonl` unions them; each manifest discovers its own `charr.toml`.
- **Per-config budget.** `--configs N` selects the number of sampled configs; `--samples` keeps its meaning - cases *per
  config* - so total images = N x samples. Each config independently stratifies all 20 cells (the
  [ADR-0014](0014-stratified-generation-model.md) allocation is unchanged), so each subdirectory is a valid standalone
  eval unit.
- **Retire the single global canonical style.** [ADR-0018](0018-generator-structure-recipe-registry.md)'s
  `canonical_palette()` / `canonical_fonts()` singletons are replaced by the per-config sampler. There is no privileged
  house style anymore; an `N=1` run is simply one sampled config, seed-deterministic.
- **Within a config the Phase 1 split is unchanged.** The palette and font expectation are fixed (label-bearing,
  config-controlled); within-palette colour choice and within-family concrete font stay label-neutral jitter.

Alternatives considered:

- **Curated house-style bundles** (each a hand-paired palette + font): rejected. It models a reviewer with taste, not a
  rule-checker; it teaches the model a small fixed set of "good" styles, and it breaks the total role-rotation that is
  the whole point of the slice.
- **A full palette x font matrix as the primary model:** rejected as the mechanism, though it is the limiting case of
  independent sampling. Independent sampling subsumes a matrix without enumerating a combinatorial explosion and without
  forcing incoherent fixed pairs; a deterministic matrix *mode* could be added later if exhaustive coverage is ever
  wanted.
- **Randomize palette/font within a single dataset:** rejected. With no single declared expectation, `palette-compliance`
  and `font-compliance` have nothing to judge against and become meaningless.
- **Allow empty ("anything goes") configs for an even stronger anti-prior:** rejected for generation. An empty palette
  makes the palette cells unservable in that config and weakens coverage to a union property. The concern that motivated
  it - rules enabled but nothing configured - is a checker behaviour, resolved deterministically in `charr` (issue #14),
  not a generator knob.
- **`--samples` as a grand total split across configs:** rejected. A half-covered config is a weak eval unit; a
  per-config budget keeps every dataset independently valid and the mental model simple ("each style gets a dataset of
  this size").

## Consequences

- `palette-compliance` and `font-compliance` lose their absolute-style prior: across one run the same colour or font is
  compliant in one dataset and violating in another, so the checker can only succeed by judging relative to each
  dataset's `charr.toml` - which is the behaviour we want to measure.
- A run emits N dataset directories and total images scale as N x samples. The dataset-as-directory invariant
  ([ADR-0011](0011-dataset-manifest-as-unit.md)) holds per config.
- Coverage stays a per-config guarantee (no union weakening), because palettes and font-sets are sampled non-empty; each
  config still covers all 20 cells under the unchanged [ADR-0014](0014-stratified-generation-model.md) allocation.
- The single global canonical palette/font is gone; each config's `meta.json` records its concrete sampled values, so a
  run stays reproducible and inspectable.
- Determinism restated: a run is deterministic in `(configs N, samples, seed)` for a fixed *(generator version, active
  library set)*; adding a style axis or changing the sampler shifts the RNG stream (a fine 0.x break, extending
  [ADR-0013](0013-rendering-libraries-plotly-optional.md) / [ADR-0018](0018-generator-structure-recipe-registry.md)).
- Eval is structurally unchanged (already multi-manifest). A per-config breakdown in the report - "the model fails on
  serif-expected configs" - is a possible future refinement, not required here.
- This decision depends on [ADR-0020](0020-colour-sampling-ciede2000.md) for colour distance and
  [ADR-0021](0021-bundled-fonts-and-delivery.md) for the curated font set, bundled fonts and their licence. The related
  readability rules surfaced while settling this slice -
  background-vs-series and gridline-vs-series proximity, and gridline weight - are out of scope and spun out to issues
  [#11](https://github.com/mvherweg/charr/issues/11), [#12](https://github.com/mvherweg/charr/issues/12), and
  [#13](https://github.com/mvherweg/charr/issues/13).
