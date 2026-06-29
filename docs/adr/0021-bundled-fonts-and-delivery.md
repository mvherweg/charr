# 0021. Bundled fonts: a property-distinct supported set, with delivery verified per backend

- Status: Accepted
- Date: 2026-06-29

## Context

[ADR-0019](0019-multi-config-style-sweep.md) has each style-config approve 1-3 fonts, and a font-violation chart use an
unapproved one. For ground truth to hold *by construction* ([ADR-0015](0015-ground-truth-by-construction.md)) two things
must be true: the approved fonts render faithfully, and the violation font is reliably distinguishable from *every*
approved font, so `font-compliance: fail` is true by construction. That raises two problems colour did not have: which
fonts can we trust to be mutually distinct, and does the chosen font actually render given different backends?

Forces:

- **Distinctness is hard to measure for fonts.** Unlike colour, there is no clean perceptual metric. The reliable signal
  is *structural*: typefaces that differ on a clear structural property - serif vs sans, monospaced vs proportional,
  script vs not - are unambiguously different, while two fonts sharing all those properties are not reliably
  distinguishable (Open Sans vs Montserrat in a chart).
- **Delivery differs by backend.** matplotlib/seaborn honour a registered font precisely and let us verify the resolved
  file. plotly/kaleido resolves the family name through the OS (fontconfig / CoreText in headless Chromium), so a
  bundled-but-uninstalled font silently falls back to a default - a ground-truth hazard, because every image carries a
  `font-compliance` verdict, not just the violation chart.
- **Reproducibility and licence.** A system font present on one machine and absent on another makes output
  non-reproducible and invites silent substitution ([ADR-0013](0013-rendering-libraries-plotly-optional.md)). Fonts must
  be redistributable and non-GPL, and bundled so behaviour does not drift across machines.
- **Dependencies stay minimal** and the bundle stays small.

## Decision

**We will bundle a small set of redistributable fonts, model each by its distinguishing structural properties, derive
distinctness from property difference, and guarantee faithful rendering only where we can verify it.**

- **A property-distinct supported set.** Each font is tagged with distinguishing properties: `serifs` (none vs serifed),
  `monospaced` (yes/no), `script` (yes/no). Two fonts are "reliably distinct" iff they differ on `>= 1` of these.
  Deliberately *not* weight or slant - bold or italic of a family is not a clearly different typeface, so it carries no
  compliance signal and cannot be relied on for distinctness. A *bucket* is a property tuple; the set ships `>= 1` font
  per useful bucket, and a bucket may hold *siblings* (for example a slab serif lives in the serif bucket) purely for
  compliant variety.
- **Distinctness is derived and tested, not asserted.** The violation font for a `font-compliance: fail` chart is drawn
  to differ by `>= 1` distinguishing property from *every* approved font, so the `fail` label is true by construction. A
  property test asserts each generated violation differs by a distinguishing property from all approved fonts; a registry
  test asserts the supported set spans enough buckets that any approved subset (up to three) still leaves a
  differing-bucket font available to draw a violation from.
- **Same-bucket "subtle" violations are out of scope (deferred).** Two fonts sharing all distinguishing properties are
  not reliably distinguishable, and there is no clean automatic font-distance to certify a borderline pair. Using one as
  a violation against the other would risk a `fail` label on text that looks compliant
  ([ADR-0015](0015-ground-truth-by-construction.md)). Siblings therefore serve compliant variety only, never as
  violations - the derived rule enforces this automatically (a sibling differs by zero properties, so it is never
  eligible). A human-certified subtle-violation set is a possible future opt-in, not part of the automatic guarantee.
- **Faithful delivery only where verifiable.** matplotlib/seaborn register each bundled font
  (`font_manager.addfont`), and we assert `findfont` resolves our bundled file rather than a fallback - raising loudly
  otherwise, so a misregistered font fails the run instead of mislabelling an image. plotly/kaleido cannot be trusted to
  render a bundled-but-uninstalled font, so plotly images carry `font-compliance: not_applicable` - a *backend-driven*
  NA, the same shape as the chart-type-driven NA already in use (a pie's NA for axis rules,
  [ADR-0018](0018-generator-structure-recipe-registry.md)). The `font-compliance` pass/fail cells are therefore assigned
  to matplotlib/seaborn. Colour fidelity is unaffected - plotly takes explicit colour values - so the palette axis stays
  cross-backend.
- **Bundled in-repo, redistributable licences.** The `.ttf` files live as package data under `charr-datagen` (found via
  `importlib.resources`), regular weight only to start, under OFL or Apache-2.0 (permissive, non-GPL), with each font's
  licence shipped in a `LICENSES/` notice. We bundle rather than fetch: OFL/Apache explicitly permit redistribution, and
  bundling is what makes rendering reproducible across machines - fetching would re-introduce the cross-platform drift we
  are removing, for no licence benefit.

Alternatives considered:

- **Hand-pick visually distinct families (no property model):** rejected in favour of the property model, which turns
  distinctness into a derived, testable predicate rather than a per-pair judgement, and cleanly supports sibling fonts
  for compliant variety. The hand-picked list was the earlier proposal; the property model subsumes it.
- **Same-bucket subtle violations for extra difficulty:** rejected for now (above) - no automatic distinctness guarantee;
  revisit as a human-curated opt-in if subtle font discrimination becomes a target.
- **Make kaleido discover bundled fonts (fontconfig / user font dirs):** rejected. kaleido custom-font support is fragile
  and OS-specific, the workaround mutates global machine state, and plotly is already best-effort and optional
  ([ADR-0013](0013-rendering-libraries-plotly-optional.md)). Not worth the fragility for a guarantee we get cleanly via a
  backend-driven NA.
- **Map plotly text to generic CSS families (`serif` / `sans-serif` / `monospace`):** rejected. Chromium renders generics
  faithfully, but that judges fonts only at the category level while the rule and the config name *specific* families, so
  a plotly image in Chromium's default serif against an approved specific serif is a mismatch the rule cannot reconcile.
- **System fonts, or fetch-on-install:** rejected. Non-reproducible across machines and prone to silent substitution;
  bundling is licence-clean and deterministic.
- **A font-shaping / metrics dependency to measure similarity:** rejected. Overkill, and it still would not give a
  trustworthy "are these two distinguishable in a chart" answer; the structural property model is simpler and honest
  about exactly what it guarantees.

## Consequences

- `font-compliance` gets by-construction ground truth on matplotlib/seaborn: a compliant chart uses approved fonts
  (verified resolved), and the violation differs by a distinguishing property from all of them. On plotly the verdict is
  an honest `not_applicable` rather than an unverifiable claim.
- Backend assignment becomes cell-aware for the font cells (they render on matplotlib/seaborn); colour and the other
  rules stay cross-backend.
- Adding a font is appending one record (file plus properties) under the right bucket; the registry test validates
  coverage. The supported set stays small and redistributable.
- A new backend-driven NA axis exists, generalizing the type-driven NA of
  [ADR-0018](0018-generator-structure-recipe-registry.md). The eval 3-class substrate already handles NA
  ([ADR-0017](0017-eval-metrics-from-confusion-substrate.md)), so no eval change is needed.
- The dataset's `charr.toml` is unchanged in shape (a list of approved font names); the checker needs no knowledge of the
  property model - properties are a generation-side device for sampling distinct violations.
- The repo carries a handful of `.ttf` files (~1-3 MB) and a `LICENSES/` notice; no new runtime dependency.
- This completes the style-config mechanics opened in [ADR-0019](0019-multi-config-style-sweep.md); colour is
  [ADR-0020](0020-colour-sampling-ciede2000.md). Together they let palette and font vary independently per config while
  ground truth stays exact.
