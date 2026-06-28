# 0018. Generator structure: a data-driven chart-type registry with label-neutral variety

- Status: Accepted
- Date: 2026-06-28

## Context

The MVP generator ([ADR-0014](0014-stratified-generation-model.md), shipped in PR #5) renders charts from a single
`if/elif` dispatch over `(rule, polarity)`, with one chart vocabulary, three chart types, a fixed palette and font, and
identical pass-cases. That is the minimum-variety floor: a dataset so monotonous the checker could pass it by memorizing
our house style rather than judging chart content. Raising variety is the next slice ([issue #7](https://github.com/mvherweg/charr/issues/7)).

The tension is real. More variety means more moving parts, and every moving part is a place a ground-truth label can
silently go wrong - and ground truth is trusted by construction ([ADR-0015](0015-ground-truth-by-construction.md)), with
no programmatic re-derivation from the image to catch a mistake. So the structure has to make **correctness local and
checkable** while making **extension cheap** (the explicit goal: adding a chart type or a domain should be a small local
change, not surgery across a dispatch).

Forces:

- **Two kinds of knob.** Some knobs are *label-bearing* - changing them changes a verdict (title / axis-label / units /
  legend presence, palette and font compliance, zero baseline). Others are *label-neutral* - they change nothing about
  any verdict (the chart's subject vocabulary, the numbers, color shades within the allowed hues, the concrete font
  within the expected family, figure size, gridlines, markers, orientation, and which chart type draws a rule that
  several types can carry). Almost all the missing variety lives in the label-neutral axes, which is exactly the variety
  that is free and safe.
- **Most violations are not type-specific.** Dropping the title, using a serif font, using off-palette colors, removing
  axis units - these operate on shared scene fields and are identical across every chart type. Only a few are
  type-specific (a non-zero baseline only means something for bars; overlap is induced differently per type).
- **Some rules cannot apply to some types.** A pie/donut has no axes, so `axes-labeled` / `axis-units` / `zero-baseline`
  are `not_applicable`; a line chart's value axis is not expected to start at zero, so `zero-baseline` is NA there. A
  type must be able to say "this rule is structurally impossible for me."
- **Correctness should not be guarded at runtime by re-deriving truth from pixels** (ADR-0015), and a generative test
  keyed on a seed risks spooky failures when an unrelated change shifts the RNG stream into an edge case.

## Decision

**We will restructure generation as a registry of data-driven chart-type recipes, composed with an in-code domain
registry and uniform label-neutral randomization, and enforce correctness and coverage with seed-robust tests rather
than runtime checks.**

- **Compose orthogonal axes.** A case is built as: take the target `(rule, polarity)` cell -> pick a chart type that can
  serve it -> sample a domain for vocabulary, units, and value ranges -> apply label-neutral style jitter -> emit
  `(scene, labels)`. This replaces the `(rule, polarity)` dispatch.
- **Label-bearing knobs are recipe-controlled; label-neutral knobs randomize freely (seeded).** This split is the
  invariant that keeps ground truth exact while variety scales: the random draws never touch a verdict, so a chart's
  labels are a function of its `(cell, type)` alone, independent of the seed.
- **Chart types are data, not objects.** A chart type is a dataclass: a compliant-baseline builder, a `na_rules` set
  (rules structurally impossible for the type), and a table of type-specific defect injectors. Global defects live in a
  shared default table; a type's effective injectors are the global table merged with its own overrides, minus its
  `na_rules`. Adding a type is appending one dataclass (plus any type-specific injector); "which cells a type can serve"
  is *derived* from `na_rules` and the injector keys, not declared separately.
- **Domains are an in-code registry.** A domain is a dataclass (title templates, categories, series names, unit, value
  range) in one list; adding a domain is appending a literal. Not external data files - charts need code to render, so
  types cannot be pure data, and keeping domains in-code stays typed and refactor-safe. A file-backed loader can be
  added later without changing the concept.
- **Correctness and coverage are enforced by tests + docs, not runtime guards**, and the tests are seed-robust:
  - **Coverage** ("every `(rule, polarity)` cell is servable by at least one type") is checked by **pure inspection of
    the registry metadata** - set operations over `na_rules` and injector keys, with no generation, no seed, and a
    precise failure message. It cannot be perturbed by an unrelated change.
  - **Label correctness** is checked by calling the real recipe and asserting the resulting label vector against the
    metadata-derived expectation. Because labels are seed-invariant (the split above), any fixed seed suffices; a small
    meta-test asserts the label vector is *identical across several seeds*, proving label-neutrality directly.
  - These checks are **image-blind** - they inspect label bookkeeping and registry structure, never re-derive a verdict
    from pixels - so they are compatible with ADR-0015, which only rejected image-based self-checking.

Alternatives considered:

- **Keep the `(rule, polarity)` dispatch:** rejected. Correctness must be reasoned about globally, every new type edits
  every branch, and it is hostile to the extension goal that motivates the slice.
- **Chart types as a class hierarchy (inheritance) for "global default + override":** rejected in favor of a default
  table. A chart type has no real behavior beyond data and a few functions, so a dataclass plus a dict merge expresses
  "global default, override when needed" with less ceremony, and the effective injectors are read from one explicit
  merge rather than reconstructed across a class's MRO. Inheritance would also work and the hierarchy would be shallow;
  it loses on grain (the codebase is data + functions) and transparency, not on correctness.
- **Data-driven (file-backed) chart types and domains:** rejected for now. Types need code to render, so a data format
  would become a chart mini-language; domains are kept in-code (typed, no new format) and can graduate to a loader later
  if non-developers ever need to add them.
- **Runtime / startup invariant and coverage checks:** rejected in favor of generic, registry-driven tests plus a dev
  doc. Tests carry no per-run cost, match the "the gate is the PR / tests" philosophy, auto-cover new types and domains,
  and give debuggable failures; a startup guard would re-cost every user run and offer false security between releases.
- **A separate fuzz/smoke test** ("generation never crashes or produces a degenerate chart") is acknowledged as
  inherently seed-sensitive and is kept *separate and clearly labeled*, so a failure there reads as "some input breaks
  generation," never confused with the coverage or label invariants.

## Consequences

- Adding a chart type is one dataclass (baseline + `na_rules` + any type-specific injectors); adding a domain is one
  dataclass literal. The generic coverage and label tests validate the addition automatically, and the coverage test
  fails loudly with a precise message if a new rule leaves a cell unservable.
- Variety scales on the label-neutral axes essentially for free, while ground truth stays exact - the split is what
  buys both at once.
- Existence and correctness tests have **no spooky seed coupling**: coverage is structural metadata, and labels are
  seed-invariant by construction. Only the optional crash-fuzz test is seed-sensitive, by its nature, and is isolated.
- One-time cost: the MVP `cases.py` is refactored into the registry. The cell catalog and allocation
  ([ADR-0014](0014-stratified-generation-model.md)) are unchanged - chart type is a within-cell choice, not a new
  stratum.
- Determinism is restated cleanly for future readers: generation is deterministic within a fixed *(generator version,
  active library set)* - same inputs and code give byte-identical output - but a seed is **not** a stable identifier
  across code changes; adding a label-neutral axis shifts the RNG stream and changes which charts a seed yields (a fine
  0.x break, extending ADR-0013's "per active library set").
- Relations: palette/font variety across *configs* is deferred to a multi-config manifest sweep (Phase 2 of issue #7,
  its own ADR, building on [ADR-0011](0011-dataset-manifest-as-unit.md)); more chart types are later registry appends
  (Phase 3).
- This would be revisited if a chart type genuinely cannot fit the `{baseline, na_rules, defects}` contract, if
  non-developers need to author domains (a data-backed loader), or if per-type frequency weights become necessary (an
  optional field on the type, not a structural change).
