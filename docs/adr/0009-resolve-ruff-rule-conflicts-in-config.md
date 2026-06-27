# 0009. Resolve Ruff's unsatisfiable rule conflicts in config

- Status: Accepted
- Date: 2026-06-28

## Context

The lint policy is `select = ["ALL"]` with no global ignores (findings are silenced case by case with inline `# noqa`).
But `ALL` pulls in rules that are mutually exclusive, so Ruff cannot satisfy them and prints a warning on every run:

- `D203` (blank line before class docstring) vs `D211` (no blank line before class docstring).
- `D212` (multi-line summary on the first line) vs `D213` (summary on the second line).

It also pulls in `COM812` (trailing comma), which Ruff flags as conflicting with the formatter and recommends disabling.

These warnings are not findings we can fix in code; they are configuration conflicts Ruff explicitly asks us to
resolve. Left alone they add noise to every `ruff check` / `ruff format` run.

## Decision

Add a small `lint.ignore` listing exactly the rules Ruff already discards or recommends disabling: `D203`, `D213`, and
`COM812`. We keep `D211` and `D212` (the halves our docstrings already follow), and the formatter keeps managing commas.

This is a narrow, sanctioned exception to "no global ignores": it resolves Ruff's own unsatisfiable conflicts, it does
not silence any real finding, and every entry carries a comment explaining the conflict. The blanket prohibition still
holds for everything else (use inline `# noqa`), and the test relaxations remain in `per-file-ignores`.

## Consequences

- `ruff check` and `ruff format` run cleanly, with no warnings.
- Docstring style stays enforced via `D211`/`D212`; nothing about the code changes.
- A future reader should not remove these ignores (the warnings would return) nor read them as license for broad
  ignores to dodge findings.
