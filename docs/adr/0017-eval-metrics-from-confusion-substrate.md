# 0017. Score per rule from a 3-class confusion substrate; fail-class precision/recall as the headline

- Status: Accepted
- Date: 2026-06-28

## Context

`charr-eval` scores the checker against a labeled dataset. Per rule, each image has a ground-truth verdict and the
checker's predicted verdict, both in `{pass, fail, NA}` (the dataset is multi-label - every image is labeled against
every rule, per [ADR-0016](0016-multi-label-chart-dataset.md)). So scoring a rule is a 3-class problem, and
"precision/recall per rule" is underspecified until we name the class it is measured on.

Two further forces:

- The checker's job is to **catch violations**. The two costly errors are *missing a real problem* and *crying wolf*,
  which map exactly to recall and precision on the violation class.
- [ADR-0010](0010-three-packages-eval-drives-charr.md) set a "raw output, presentation later" principle (the
  code-coverage analogy): capture the checker's actual outputs so failure modes are investigable, and keep presentation
  a thin layer. A planned separate "raw-output capture" decision turns out to be the application of this principle here,
  not an independent choice.

## Decision

**Score every rule from a raw confusion substrate, and report decision-relevant scalars derived from it.**

- **Substrate (raw, persisted).** For each `(manifest, image, rule)` record the ground-truth verdict, the checker's
  predicted verdict, and the checker's captured raw output. Aggregate into a **3-class confusion matrix per rule** over
  `{pass, fail, NA}`, plus an `error` bucket for output that could not be parsed into a verdict. This substrate is the
  failure-analysis artifact; it is keyed so it can be sliced per manifest (the reported dimension of
  [ADR-0011](0011-dataset-manifest-as-unit.md)) as well as per rule.
- **Positive class is `fail`.** The headline metrics, all *derived from the substrate*, are per-rule **precision and
  recall on the `fail` class** (real violations caught vs. false alarms), per-rule **accuracy**, and an **overall
  macro-average across rules** (each rule weighted equally). F1, micro-average, and NA-specific numbers are further
  derived views, neither computed separately nor stored separately.
- **Errors are folded in, never dropped.** A `(rule, image)` with no parseable verdict lands in the `error` bucket and
  counts as a non-detection: a real-`fail` image where the checker errored is a missed violation. A flaky endpoint thus
  shows up as errors rather than masquerading as passes.
- **Every metric is a pure function of the substrate.** Presentation never re-runs the checker; adding a new metric is a
  downstream view, never a new run.

This also settles what would have been a separate raw-output-capture ADR: the substrate *is* that capture, a direct
application of ADR-0010's principle, recorded here rather than in its own file.

Alternatives considered:

- **Accuracy only, per rule:** rejected. Accuracy hides the asymmetry between missing a violation and raising a false
  alarm - the two failure modes that matter for a checker - and is misleading under class imbalance.
- **Per-class precision/recall for all three classes as the primary headline:** rejected *as the headline* (kept as a
  derived view). `fail` is the action class; promoting `pass` and `NA` precision/recall to primary multiplies the
  numbers to read without matching the checker's purpose, while the 3-class confusion substrate still preserves them.
- **Micro-average as the overall:** rejected as the headline. We weight each rule equally, not by sample count; micro
  stays derivable, and with balanced generation (ADR-0014) the two nearly coincide anyway.
- **Storing only the headline scalars (not the substrate):** rejected. It discards the failure-mode detail ADR-0010
  requires and would force re-running the checker to investigate a mistake.

## Consequences

- The metrics that matter for a checker - precision and recall on violation detection - are front and center per rule,
  with a single macro-average overall.
- The per-image substrate doubles as the failure-analysis log (which images and rules the checker got wrong, with its
  raw output), ready for inspection and for the review GUI in [issue #4](https://github.com/mvherweg/charr/issues/4).
- Any further metric (F1, micro-average, per-class P/R, NA recall) is a downstream view; adding one never needs a re-run.
- No separate ADR is needed for raw-output capture; it lives here.
- This would be revisited if a different positive-class framing (e.g. making NA detection a first-class target) or a
  confidence-aware metric became necessary.
