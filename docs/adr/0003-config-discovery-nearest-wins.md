# 0003. Config discovery is nearest-file-wins, not cascade-merge

- Status: Accepted
- Date: 2026-06-27

## Context

Charr reads config from a standalone `charr.toml` or the `[tool.charr]` table of a `pyproject.toml`, discovered by
walking up from the working directory. There are two established models for "walk up" config:

- **Nearest single file wins** (Ruff, Black, Prettier): pick the closest config and stop; no implicit merge.
- **Cascade-merge** (EditorConfig, legacy ESLint, and pattern-wise `.gitignore`): combine every config encountered up
  the tree, with the closest setting winning per key, usually stopping at a `root` sentinel.

The split tracks what the file is: per-subtree pattern/rule files cascade; project tool-config picks a single nearest
file. Charr's config is project-level tool settings, and Charr resembles a Python project linter.

## Decision

We will use **nearest single file wins**. `discover_config_file` walks up and returns the first config found (closest
`charr.toml`, else closest `pyproject.toml` containing `[tool.charr]`). No merging across ancestors.

Cascade-merge was considered and rejected for now because it forces several non-obvious calls: whether list fields
(`enable`, `disable`, `palette`, `fonts`) replace or concatenate on merge; a `root = true` stop sentinel so a subdir
does not inherit from `$HOME` or unrelated ancestors; and turning precedence into a documented contract.

## Consequences

- Matches the Python-linter family users already expect; simplest behavior to reason about.
- Avoids the list-field and precedence questions above entirely.
- Accepted downside: a deep config fully shadows ancestors. A deep `charr.toml` that sets only `fonts` does not inherit
  a repo-root `palette`.
- If inheritance is wanted later, add **explicit** composition (Ruff-style `extend = "..."`), never an implicit cascade.
  That would be a new ADR superseding this one.
