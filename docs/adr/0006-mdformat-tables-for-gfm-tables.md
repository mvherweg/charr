# 0006. Enable GFM tables in mdformat via the mdformat-tables plugin

- Status: Accepted
- Date: 2026-06-27

## Context

Markdown is formatted and CI-checked with mdformat (`uv run mdformat --check`). Plain mdformat speaks CommonMark, which
has no table syntax, so it silently reflows a GFM pipe table into a wrapped paragraph. This was discovered when an ADR
index table was mangled by formatting. Tables are wanted in the docs (the ADR index, comparison tables), and they must
survive `mdformat --check` rather than being destroyed by it.

## Decision

We will add the **`mdformat-tables`** plugin as a dev dependency. mdformat auto-discovers installed plugins, so
`uv run mdformat` and the CI check both gain GFM-table support with no config change; the plugin only needs to stay in
the dev-dependency group. The plugin constrains mdformat to its compatible 0.7.x line, which still satisfies the
existing `mdformat>=0.7` pin.

Alternatives considered: **mdformat-gfm** (full GFM: tables plus strikethrough, autolinks, task lists) was rejected for
now as a broader surface and behavior change we do not need; only tables are required. Avoiding tables entirely was
rejected because tables are genuinely wanted in the docs.

## Consequences

- GFM pipe tables round-trip cleanly and pass CI.
- Small added surface (`mdformat-tables` and its `wcwidth` dependency), MIT-licensed.
- mdformat is held on the 0.7.x line the plugin supports; revisit if we want mdformat 1.x.
- If we later want other GFM features (strikethrough, task lists, autolinks), switch to `mdformat-gfm` in a new ADR.
