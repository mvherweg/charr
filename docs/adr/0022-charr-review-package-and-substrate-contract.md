# 0022. A separate `charr-review` package consuming the eval substrate as a contract

- Status: Accepted
- Date: 2026-06-30

## Context

`charr-eval` writes a confusion substrate ([ADR-0017](0017-eval-metrics-from-confusion-substrate.md)): one JSONL record
per `(manifest, image, rule)` carrying the ground-truth verdict, the checker's predicted verdict, the model's raw
rationale, and any error. It is the persisted failure-analysis artifact, and ADR-0017 already earmarks it for "the
review GUI in issue #4".

We are building that front-end: a tool to walk an eval run image-by-image and see, per rule, the expectation, what the
model predicted, and why. Two structural questions precede any code: where does this tool live, and how does it get the
shape of a substrate record?

The forces:

- The repo keeps **one concern per package** (`charr` checks, `charr-datagen` generates, `charr-eval` scores; see
  [ADR-0001](0001-uv-workspace-two-packages.md), [ADR-0010](0010-three-packages-eval-drives-charr.md)). `charr-eval` is
  a lean, pure-offline scorer with no UI, web, or static-asset concerns.
- There is an established precedent for sharing a data shape across packages **without** a code dependency:
  `charr-datagen` and `charr-eval` each declare their own `ManifestRecord` rather than import the other, treating the
  manifest JSONL as a tool-agnostic contract (ADR-0010). The substrate is the symmetric case - `charr-eval`'s output
  rather than its input.
- The `SubstrateRecord` model lives in `charr_eval.scoring`, next to the metrics code, not in a published-schema module.

## Decision

We will add a fourth workspace package, `charr-review`, for the review front-end. It will **depend only on `charr`**
(for `Verdict`, `RuleId`, `CharrError`), not on `charr-eval`. It re-declares the substrate record as its own model and
reads the JSONL directly, treating the substrate as a **published contract** - the same dependency-avoidance pattern
ADR-0010 chose for the manifest.

Alternatives considered and why they lost:

- **Import `charr_eval.scoring.SubstrateRecord`.** Least code, but couples a UI package to eval's internals, which sit
  beside the scoring math; a refactor of eval's metrics could ripple into the reviewer for no good reason.
- **A `charr-eval serve` subcommand (no new package).** Fewest moving parts, but it bolts a web server, static assets,
  and browser-launching onto a tool whose single concern is offline scoring, enlarging its dependency surface and
  blurring the package split the repo has held to.

Because the substrate is now an explicit cross-package contract rather than an implementation detail of eval, its format
must be **documented in the repo docs** (issue #21, part of the docs effort in #9).

This ADR does not supersede ADR-0017 (which defines the substrate and the metrics derived from it); it adds the
contract-and-consumer dimension. The review tool's own form factor is decided separately in
[ADR-0023](0023-flask-for-charr-review-web-app.md).

## Consequences

- Easier: `charr-eval` stays lean; `charr-review` can evolve (and later gain the curation / label-edit mode tracked in
  issue #4) without touching eval; and the reviewer can open a substrate produced by any conforming tool, matching the
  openness ADR-0010 wanted for datasets.
- Harder, knowingly accepted: a small (~7-field) record model is duplicated between `charr-eval` and `charr-review`, so
  a change to the substrate shape must be mirrored in both places. The mitigation is the same as for the manifest: a
  documented contract (issue #21) plus tests on each side. There is also one more package's `pyproject.toml` and version
  to maintain.
- Revisit when: the substrate format starts changing often, or a third consumer appears - at that point promote the
  contract to a shared schema module instead of duplicating it.
