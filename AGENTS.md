# AGENTS.md

Charr: a CLI checker that lints chart images against a rule set using (local) LLMs. Context: see
[project.md](project.md) (what and why) and [development.md](development.md) (setup, layout, workflow).

## Environment

- Python 3.13+, managed with **uv**. Run everything via `uv run ...`.
- uv workspace; two packages under `packages/`: `charr` (checker CLI), `charr-datagen` (data generator). They are
  independent on purpose.

## Checks (CI on the PR is the gate; no forced local hooks)

Run these locally when practical; CI runs the full set on every PR:

- `uv run ruff format .`
- `uv run ruff check .`
- `uv run pyright`
- `uv run mdformat $(git ls-files '*.md')`
- `uv run pytest`

## Code style

- **ASCII only** in all markdown and code. No em-dashes, emoji, smart quotes, or non-ASCII symbols (write `<=`, `->`).
- Line length **120** for code and markdown alike (links may force exceptions). **2-space indent** (not 4).
- Full type hints, new-style (`X | None`, never `Optional`).
- Ruff: all rules enabled; silence case by case **inline** with `# noqa: <code>`. Do not add global ignores (tests are
  the only sanctioned exception, already configured).
- Prefer fewer, larger, coherent files over many tiny ones.
- Dependencies: minimal and MIT-compatible; avoid GPL. Add a dep only when first used.

## Tests

- pytest, with long descriptive test names.
- Mock the LLM endpoint; tests run offline and deterministically.

## Versioning

- 0.x for now: prefer clean design over backwards compatibility. Break the public API consciously and note how callers
  adapt.

## Working style

- Honesty over pleasing. No flattery. If a better approach exists, say so with reasons.
- Do not commit or push unless asked. Branch off `main`; never commit directly to `main`.
