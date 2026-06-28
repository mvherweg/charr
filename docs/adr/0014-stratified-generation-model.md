# 0014. Generate cases by stratified allocation with seeded within-cell randomization

- Status: Accepted
- Date: 2026-06-28

## Context

`charr-datagen` fabricates labeled charts so `charr-eval` can measure the checker's per-rule, per-polarity
precision/recall/accuracy. The labels are known by construction. The question is how a run turns a budget of `--samples N` into N concrete cases.

Two models were weighed:

- **Pure i.i.d. sampling:** draw each case independently from a distribution over `(rule, polarity, library)`. Simple,
  and it never contradicts itself when N is small. But realized per-cell counts are noisy, the rarest cells (a
  conditional `not_applicable`) are easily undersampled or missed entirely at small N, and there is no natural
  population to be representative *of* - we are constructing test conditions, not sampling charts from the wild.
  (Representativeness of real charts is the job of private datasets, per [ADR-0010](0010-three-packages-eval-drives-charr.md).)
- **Stratified allocation:** control counts so each reported cell gets balanced, comparable coverage, which is what a
  measurement artifact wants.

Eval reports metrics per rule and per polarity within a rule; it does not report per-library as a primary metric.
`--samples N` is one total budget (N images), not a per-cell or per-library multiplier.

A concern with stratification is the cell count: if every axis is a stratum, the must-cover set explodes and a small N
cannot cover it. That concern is mostly self-inflicted by over-stratifying.

## Decision

We will generate by **stratified allocation over the reported axes, with seeded randomization within each cell.**

- **Stratify only `(rule, polarity)`** - about 18 to 22 cells. Library and all chart parameters (data values, colors,
  layout, the concrete way the rule is satisfied or violated) are randomized *within* a cell, seeded; library is not a
  stratum (its draw may be round-robined within a cell for balance). This keeps the must-cover set small, so an
  under-budget run is rare rather than routine.
- **Allocate by apportionment** over a priority-ordered cell list: each cell gets `floor(N / cells)`, and the remainder
  is handed out round-robin down the priority order. Deterministic given the seed.
- **Under-budget (N below the must-cover count): warn and proceed by default.** Cover the highest-priority cells the
  budget allows; log which cells are uncovered and the minimum N for full coverage; eval reports uncovered cells as *not
  sampled*, never as silently passed or truncated. Priority order: each rule's `fail` then `pass` before any
  `not_applicable`, in rule-id order. A `--strict-coverage` flag (a thin variant of the same coverage check) instead
  errors with the required minimum N.
- **Everything is deterministic in `(N, seed, config)`:** both the allocation and each cell's concrete content are
  seeded, so a dataset is reproducible (within a fixed active library set, per [ADR-0013](0013-rendering-libraries-plotly-optional.md)).

Alternatives considered:

- **Pure i.i.d. sampling:** rejected for a measurement artifact. Noisy per-cell counts and possible missed required
  cells at small N, with no representativeness benefit to offset it. Even at small N, priority-stratified coverage
  strictly dominates i.i.d. (it covers N distinct high-priority cells rather than risking N draws of one rule).
- **Stratify on `(rule, polarity, library)`:** rejected. It roughly triples the cell count, making the under-budget
  problem routine, all to balance a per-library breakdown that eval does not report as a primary metric.

## Consequences

- Per-rule and per-polarity metrics get balanced, comparable sample sizes, and required cells are covered whenever the
  budget allows - satisfying the "cover all 8 rules, including `not_applicable` where applicable" acceptance criterion.
- The under-budget case is rare (only ~20 must-cover cells) and is handled transparently rather than by silent
  truncation; `--strict-coverage` is available for callers who want a hard contract.
- Library balance and chart variety come from within-cell randomization, so the single `--samples` knob stays a true
  total.
- More moving parts than i.i.d. (an allocation policy and a priority order), but all deterministic and directly
  testable offline.
- This model assumes one targeted issue per image (the MVP simplification of ADR-0016). Supporting multiple issues per
  image, which is the intended direction, refines this allocation: the unit becomes a label vector that must cover
  meaningful combinations rather than one cell per image. See ADR-0016 and [issue #3](https://github.com/mvherweg/charr/issues/3).
- This would be revisited if a per-library breakdown became a primary report (which would promote library to a stratum),
  or if a realistic-distribution synthetic mode were ever wanted.
