# 0025. `charr-eval` is a pure scorer of a saved check output

- Status: Accepted
- Date: 2026-07-01

## Context

[ADR-0010](0010-three-packages-eval-drives-charr.md) made `charr-eval` *drive* the checker: it takes a Charr
config/model, runs `run_check` over a labeled dataset, and scores the verdicts. That ADR deliberately kept an internal
seam between *running* (produce predictions) and *scoring* (compare to labels), and said the decision "would be
revisited... if a pure external-prediction scorer became a primary use case (at which point the internal run/score seam
is promoted to a package boundary)."

That point has arrived. Coupling scoring to a live checker run means every evaluation re-runs the slow, credentialed,
LLM-backed checker; you cannot score a check result produced separately, cannot re-score without re-checking, and
cannot score predictions produced elsewhere.

## Decision

`charr-eval` becomes a **pure scorer**. It consumes a **saved `charr check` output** (the JSON `Report` on stdout) plus
the labeled manifests, joins them by image, and scores. It no longer runs the checker: no LLM client, no
`CHARR_LLM_*`, no `--model`, no checker-config discovery. `charr check` is the sole producer; the two compose
(`charr check ... > preds.json` then `charr-eval preds.json labels.jsonl`).

- **Dependency direction is unchanged** (ADR-0010): `charr-eval` still depends on `charr`, now for **models only**
  (`Report`/`RuleVerdict`/`Verdict`/`RuleId`) - `charr.models` has no I/O or LLM code. It still does not depend on
  `charr-datagen`.
- **Image identity for the join = resolved absolute path**, matched between `manifest.resolve_image` and a single new
  seam, `predictions.prediction_image_key` (`Path(image).resolve()`). `charr check` already emits absolute resolved
  paths, so the two agree with no base-directory flag. This is the same "one swappable seam" shape as
  `manifest_display_name` ([ADR-0024](0024-eval-manifest-discovery-and-naming.md)); a declared image id may replace it
  later ([#31]).
- **Mismatch handling is asymmetric.** A manifest image with no matching prediction is a per-cell gap: it folds into
  the `error` bucket (exit 0), consistent with [ADR-0017](0017-eval-metrics-from-confusion-substrate.md)'s "never drop
  a cell." A prediction image matched by no manifest means the two inputs do not correspond: a hard error (exit 2).

Alternatives considered:

- **Keep driving the checker** (ADR-0010's model): rejected as the primary mode - it forces an LLM run and credentials
  for every score and cannot score externally-produced or saved predictions. `charr check` still provides the run
  side; eval just no longer owns it.
- **A base-directory flag for the join**: rejected - `charr check` already writes absolute resolved paths, so the keys
  agree without one.
- **Declare a stable image id now** (identity independent of filesystem path): deferred to [#31], same posture as
  ADR-0024's naming seam. Path-as-identity is adequate while the project is personal; a moved dataset is a find-replace
  away, and the seam localizes the eventual change.

## Consequences

- Scoring is offline and dependency-light: no network, no credentials, no rendering stack. Re-scoring or scoring
  third-party predictions costs nothing.
- The run and score halves are now separate tools the user composes; config sweeps become "run `charr check` per
  config, then score each output" rather than one eval invocation.
- eval no longer discovers each dataset's `charr.toml`; the config that shaped the verdicts is whatever `charr check`
  used when the report was produced. [ADR-0019](0019-multi-config-style-sweep.md)'s passing note that eval discovers
  the per-dataset config is thereby superseded in operational detail (that ADR's own decision stands).
- The substrate format (ADR-0017) and the `charr-review` contract
  ([ADR-0022](0022-charr-review-package-and-substrate-contract.md)) are unchanged.
- This refines ADR-0010; it does not supersede its dependency-direction or three-package decisions.

[#31]: https://github.com/mvherweg/charr/issues/31
