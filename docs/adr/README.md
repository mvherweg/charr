# Architecture Decision Records

This directory records the **decisions** behind Charr: choices between real alternatives, with their context and
consequences. It is the version-controlled trace for everyone working on the repo, humans and agents alike.

Read this for "why is it this way"; read [AGENTS.md](../../AGENTS.md) and [development.md](../../development.md) for the
always-on conventions ("how to write code here"), and [project.md](../../project.md) for what Charr is and why.

## What belongs here (and what does not)

- An ADR captures a **decision with alternatives** (X over Y) and the trade-offs we accepted. One decision per file.
- Conventions and rules (ASCII-only, public-code-first, line length, the check suite) live in `AGENTS.md` /
  `development.md`, not here.
- ADRs are immutable once Accepted. To change one, add a new ADR and mark the old one `Superseded by [ADR-XXXX](...)`.

## Plan the decisions before the code

Before implementing a non-trivial piece of work (a vertical slice, a new package, a data format), list the decisions
that will likely spawn an ADR and put them at the top of the tracking issue. A decision earns a spot when it picks
between real alternatives with lasting consequences - a dependency direction, a file format, a library, a metric - not
when there is an obvious default. Then work through them one at a time: state the trade-off, take a position, resolve the
open questions, and write each ADR as it settles. Code follows settled decisions, so the "why" is captured while the
alternatives are still live instead of being reverse-engineered in code review.

## How to add one

1. Copy [0000-template.md](0000-template.md) to `NNNN-short-kebab-title.md` with the next free number.
2. Fill in Context, Decision, Consequences. Set Status to `Accepted` (or `Proposed` if still under discussion) and the
   date.
3. Add a row to the index below.
4. Keep it ASCII-only, wrapped at 120, and run `uv run mdformat docs/adr/*.md` before committing.

## Index

| ADR  | Title                                                                                                                       | Status   |
| ---- | --------------------------------------------------------------------------------------------------------------------------- | -------- |
| 0001 | [uv workspace with two separate packages](0001-uv-workspace-two-packages.md)                                                | Accepted |
| 0002 | [Use `requests` for the LLM call, not httpx or the openai SDK](0002-requests-not-httpx-or-openai-sdk.md)                    | Accepted |
| 0003 | [Config discovery is nearest-file-wins, not cascade-merge](0003-config-discovery-nearest-wins.md)                           | Accepted |
| 0004 | [Use pydantic for models, config, and LLM response validation](0004-pydantic-for-models-and-validation.md)                  | Accepted |
| 0005 | [Credentials via environment variables; three-way exit codes](0005-env-vars-and-exit-codes.md)                              | Accepted |
| 0006 | [Enable GFM tables in mdformat via the mdformat-tables plugin](0006-mdformat-tables-for-gfm-tables.md)                      | Accepted |
| 0007 | [Markdown formatting uses wrap=keep, not auto-wrap to 120](0007-markdown-wrap-keep.md)                                      | Accepted |
| 0008 | [Request structured output via json_schema, not json_object](0008-json-schema-response-format.md)                           | Accepted |
| 0009 | [Resolve Ruff's unsatisfiable rule conflicts in config](0009-resolve-ruff-rule-conflicts-in-config.md)                      | Accepted |
| 0010 | [Third package `charr-eval` that drives the checker](0010-three-packages-eval-drives-charr.md)                              | Accepted |
| 0011 | [The dataset unit is a manifest, not an enforced directory](0011-dataset-manifest-as-unit.md)                               | Accepted |
| 0012 | [Encode the labels manifest as JSONL, not TOML](0012-manifest-encoding-jsonl.md)                                            | Accepted |
| 0013 | [Render with matplotlib, seaborn, and plotly; plotly optional](0013-rendering-libraries-plotly-optional.md)                 | Accepted |
| 0014 | [Stratified generation with seeded within-cell randomization](0014-stratified-generation-model.md)                          | Accepted |
| 0015 | [Synthetic ground truth is established by construction and trusted](0015-ground-truth-by-construction.md)                   | Accepted |
| 0016 | [The labeled-chart dataset is multi-label](0016-multi-label-chart-dataset.md)                                               | Accepted |
| 0017 | [Score per rule from a 3-class confusion substrate; fail-class P/R headline](0017-eval-metrics-from-confusion-substrate.md) | Accepted |
