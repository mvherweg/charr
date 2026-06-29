# 0020. Colour sampling for style-configs: CIEDE2000 distance with bounded-retry rejection

- Status: Accepted
- Date: 2026-06-29

## Context

[ADR-0019](0019-multi-config-style-sweep.md) has each style-config sample a palette of 1-6 colours and, for every
palette-violation chart, an off-palette colour. For ground truth to hold *by construction*
([ADR-0015](0015-ground-truth-by-construction.md)) this needs two guarantees: palette colours must be mutually
distinguishable (readable multi-series charts, and no compliant chart that accidentally "looks off"), and the violation
colour must be **unmistakably** outside the palette, so `palette-compliance: fail` is true by construction rather than by
luck. Every sampled colour must also read on the chart background (fixed white this phase).

"Sufficiently different" is a perceptual question, not an RGB one. Forces:

- **Anchor thresholds in established science.** The colour-difference JND research lives in CIELAB / CIEDE2000
  (`deltaE2000 ~= 1` is the just-noticeable difference). `deltaE76` (CIELAB Euclidean) has an established number
  (`~= 2.3`) but is perceptually *non-uniform*: one fixed threshold means different real distinctness across hues, which
  a distinctness *guarantee* cannot tolerate. OKLab is perceptually uniform and simpler to compute, but has no equally
  canonical published JND.
- **We operate well above JND** - clearly-distinct categorical colours, not sub-JND comparisons - so perceptual
  uniformity matters more than decimal precision, and the exact threshold is a calibrated band, not a sacred constant.
- **Termination must be guaranteed.** Sampling must not loop forever or paint itself into a corner.
- **Dependencies stay minimal** (no colour-science dependency unless one is genuinely needed).

## Decision

**We will sample colours in CIELAB, measure distinctness with CIEDE2000, build palettes and violations by bounded-retry
rejection within a white-legible band, and enforce the guarantees with tests.**

- **Metric: CIEDE2000.** The sRGB->CIELAB conversion and the `deltaE2000` formula are implemented inline (no new
  dependency), and the formula is **unit-tested against the Sharma et al. (2005) published reference vectors**, so its
  correctness is verified rather than assumed. This is what makes "take the complexity hit" safe: the fiddly part is
  pinned by published data.
- **Two thresholds, as `deltaE2000` constants.** `T_within` (mutual palette separation; `13`, solidly "perceptible at a
  glance" so two series never confuse) and `T_violation` (off-palette margin; `24`, well clear of `T_within` so a
  violation is never borderline). They are chosen as JND multiples and frozen with a rationale comment; `T_violation`
  was calibrated down from an initial `26` after a retry-distribution probe showed `26` gives the violation-vs-full-
  palette draw a heavy tail (a rare but real chance of exhausting the cap), while `24` keeps a ~5x retry margin. The band
  they sit in, not the exact decimal, is what matters.
- **Legible band on white.** Colours are sampled with a mid lightness and a minimum chroma, inside the sRGB gamut, so
  nothing lands near-white-on-white or as a muddy near-grey. Starting band: `L*` in `[25, 75]`, chroma `>= ~20`;
  calibratable alongside the thresholds.
- **Bounded-retry rejection, not a lattice.** A palette is built by drawing legible colours and keeping each one that is
  `>= T_within` from those already chosen; a violation by drawing a colour `>= T_violation` from *every* palette colour.
  A generous try cap (starting 256) raises a `DatagenError` with a clear message on exhaustion. The cap is a defensive
  backstop, not a working limit: a density estimate puts the legible band at roughly a couple hundred mutually-`T_within`
  distinct colours, while a chart needs at most 7 (6 palette + 1 violation, ceiling 10) - a ~30x margin, far from the
  near-full packing regime where rejection thrashes.
- **Guarantees enforced by seed-robust tests.** A property test asserts every sampled palette satisfies `T_within` and
  every violation exceeds `T_violation` from all members. A density/retry test asserts the *observed* maximum retries
  stays far below the cap at the chosen thresholds - so a wrong volume estimate fails loudly in CI, not in a user run.
  Both inspect the sampler's output and never re-derive a verdict from pixels (compatible with
  [ADR-0015](0015-ground-truth-by-construction.md)).

Alternatives considered:

- **`deltaE76` (CIELAB Euclidean):** rejected. Its JND number is established but the metric is non-uniform; a single
  threshold under-separates some hues and over-separates others, which a distinctness guarantee cannot accept. The
  established number is on the wrong metric.
- **OKLab + Euclidean distance:** a strong option - perceptually uniform and the simplest code (no piecewise step, a
  one-line distance). Rejected here only because it lacks an equally canonical published JND and this slice chose to
  anchor thresholds in established science, while CIEDE2000's formula risk is bounded by the Sharma reference vectors.
  Worth revisiting if the `deltaE2000` code proves a maintenance burden.
- **A colour-science dependency (e.g. `coloraide`):** rejected for now. The conversion plus `deltaE2000` are a contained,
  well-specified, test-validated block, and the project keeps dependencies minimal; a dependency can replace the inline
  code later without changing this decision.
- **Lattice / partition sampling (termination by construction):** rejected. It guarantees termination only by quantizing
  colour into cells, and keeping palettes natural would demand small cells, i.e. a high cell count - exactly the regime
  where the guarantee is unnecessary. The density margin makes bounded-retry rejection terminate with overwhelming
  probability, and the loud cap covers the rest.
- **A fixed curated master colour pool:** rejected. Bounded and simple, but a fixed colour vocabulary is something a
  checker could eventually learn; continuous sampling keeps the palette space open, true to the linter framing of
  [ADR-0019](0019-multi-config-style-sweep.md).

## Consequences

- `palette-compliance` gets by-construction ground truth: a compliant chart draws only palette colours (mutually
  `>= T_within`), and the single violation draws `>= T_violation` from all of them, so the label is exact without
  re-deriving it from the image.
- The package gains a small, self-contained colour module (sRGB->CIELAB, `deltaE2000`, the legible band, and the
  sampler) plus its tests, and no new third-party dependency.
- The thresholds and band are tunable constants with a recorded rationale; changing them shifts which concrete colours a
  seed yields. That is label-neutral - it never flips a verdict, because the guarantees are relative to the palette - but
  it is a fine 0.x RNG-stream break in the sense of [ADR-0019](0019-multi-config-style-sweep.md).
- The density/retry test makes the termination claim empirical: if a future threshold or band change makes the space too
  tight, CI fails rather than a user hitting the cap.
- Background is fixed white this phase; the background-vs-series and gridline-vs-series proximity rules
  ([#11](https://github.com/mvherweg/charr/issues/11), [#12](https://github.com/mvherweg/charr/issues/12)) reuse this
  same `deltaE2000` machinery when they are built.
- Fonts are the other half of a style-config and are decided separately in
  [ADR-0021](0021-bundled-fonts-and-delivery.md) (curation, licence, and per-backend delivery).
