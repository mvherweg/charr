# 0007. Markdown formatting uses wrap=keep, not auto-wrap to 120

- Status: Accepted
- Date: 2026-06-27

## Context

mdformat was configured with `wrap = 120`, which hard-wraps (reflows) prose paragraphs to 120 columns on every format
run. The side effect: editing a single sentence rewraps the whole paragraph, so small content changes produce large,
noisy diffs. That churn was the main recurring friction with our markdown tooling. The project still wants readable,
roughly 120-column markdown; the question is whether the formatter should enforce that by reflowing prose.

## Decision

We will set `wrap = "keep"` in `.mdformat.toml`. mdformat keeps existing line breaks and stops reflowing prose; it still
normalizes the rest (headings, list markers, sequential numbering, tables via `mdformat-tables`, and so on). Wrapping
prose to ~120 becomes a manual, soft guideline rather than something the formatter rewrites.

Alternatives considered: keeping `wrap = 120` (rejected: the diff churn is the actual pain); switching to PyMarkdown
(rejected in [ADR-0006](0006-mdformat-tables-for-gfm-tables.md) discussion as a larger migration that also drops
auto-wrap, trading a formatter for a linter). This decision keeps mdformat and changes one config line.

## Consequences

- Editing prose no longer rewraps whole paragraphs; markdown diffs stay small and reviewable.
- mdformat still canonicalizes structure and CI still runs `mdformat --check`, so formatting stays consistent.
- The 120-column width for markdown prose is now a manual convention, not enforced by the formatter. Code line length is
  unaffected (Ruff still enforces 120 in Python).
- Existing files already wrapped near 120 are unchanged by the switch (`keep` leaves their line breaks as-is).
