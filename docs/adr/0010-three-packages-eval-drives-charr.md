# 0010. A third package `charr-eval` that drives the checker; dependency direction

- Status: Accepted
- Date: 2026-06-28

## Context

[ADR-0001](0001-uv-workspace-two-packages.md) set up a uv workspace with two members, `charr` (the checker) and
`charr-datagen` (the generator), and explicitly foresaw that sharing a meaningful core would be "a new decision (likely
a third package)". We have now reached that point.

Iteration 2 needs to **measure** the checker: run it over charts whose correct per-rule verdicts are known and score
the result. Two facts shape where that scoring lives:

- **Evaluation must score datasets `charr-datagen` did not produce.** Generated charts lack real-world variety, so an
  org will soon feed in private datasets built from human-reviewed production cases. This is a near-term requirement,
  not a hypothetical.
- **Evaluation is a product surface, not just a dev tool.** An org that does not develop Charr may still iterate over
  different Charr *configurations* (model, rules, knobs) to see which performs best on its own labeled data. That
  audience wants to install and run the evaluator without pulling in the generator's rendering stack
  (matplotlib/plotly/seaborn/kaleido).

The tension: keeping the workspace small (two packages, less scaffolding) versus giving evaluation its own clean
boundary so it is reusable across datasets, light on dependencies, and aimed at a distinct audience.

A second axis is how *decoupled* the evaluator is from the checker. At one extreme it is a pure scorer of
`(predictions, labels)` that knows nothing about Charr; at the other it drives the checker itself. The headline use
case - "iterate over different configurations of Charr" - requires the evaluator to *run* Charr with each configuration,
which settles this axis toward the latter.

## Decision

We will add a **third workspace member, `charr-eval`**, alongside `charr` and `charr-datagen`. This extends ADR-0001's
model (one workspace, per-package runtime deps, shared dev tooling) with one more member; it does not supersede it.

Dependency direction:

- `charr` (core, checker): depends on **neither** other package. Checker users never pull `charr-datagen` or
  `charr-eval`.
- `charr-datagen` (generate): depends on `charr` (imports `BUILTIN_RULES` so labels share rule ids).
- `charr-eval` (score): depends on `charr` (uses `run_check`, `Verdict`, `RuleId`). It does **not** depend on
  `charr-datagen`.

`charr-eval` **drives the checker**: it takes a Charr config/model as a first-class input, runs `run_check` over a
labeled dataset, and scores the verdicts against the labels. It is not a pure scorer ignorant of Charr. Internally,
however, it keeps a seam between *running* (produce predictions plus captured raw outputs) and *scoring* (compare
predictions to labels), so a future "score externally-produced predictions" mode is cheap to add without being part of
this slice.

Alternatives considered:

- **Two packages, evaluation as a subcommand of `charr-datagen`** (the original ADR-0001 framing): rejected. It forces
  the rendering stack onto anyone who only wants to score, and couples evaluation to the generator - directly against
  the requirement to score externally-prepared datasets.
- **Evaluation inside `charr` core** (the checker grades itself): rejected. It serves a different audience and would
  erode the "keep the checker lean" value behind ADR-0001 and ADR-0005; the checker should not know how to grade
  itself.
- **A pure scorer that does not depend on `charr`** (maximally decoupled): rejected for the MVP because the primary use
  case is sweeping Charr configurations, which requires running the checker. The run/score seam above preserves the
  benefit (reusable scoring) without paying for a second `(predictions)` contract now.

## Consequences

- Evaluation is reusable across datasets and light on dependencies: scoring needs `charr` plus the standard library, not
  the rendering stack. The three packages have clearly distinct roles (be the checker / generate data / score against
  data), which improves separation of concerns rather than harming it.
- The **dataset format becomes a real published contract**, not an internal detail, because `charr-eval` must consume
  data that `charr-datagen` did not write. The format must therefore be hand-authorable and tool-agnostic. Its shape
  (structural model and on-disk encoding) is decided in follow-up ADRs.
- Because config/model is a first-class eval input, each eval run's output should record which configuration produced
  it, so runs are comparable. Sweeping across many configurations stays out of this slice (it is just running eval N
  times and comparing); the per-run artifact makes that future layer straightforward.
- Cost: a third `pyproject.toml` to maintain, and the datagen\<->eval contract must be written down rather than shared as
  in-memory objects. The shared `charr` types (`Verdict`, `RuleId`) soften this.
- This would be revisited if evaluation and generation turned out to need a shared core of their own, or if a pure
  external-prediction scorer became a primary use case (at which point the internal run/score seam is promoted to a
  package boundary).
