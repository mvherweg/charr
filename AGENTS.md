# AGENTS.md

Charr: a CLI checker that lints chart images against a rule set using (local) LLMs. Context: see
[project.md](project.md) (what and why) and [development.md](development.md) (setup, layout, workflow). For why things
are the way they are (decisions with alternatives and consequences), see the Architecture Decision Records in
[docs/adr/](docs/adr/README.md); record a new ADR when you make a non-obvious design choice. For a non-trivial piece of
work, identify the decisions likely to need an ADR up front (list them at the top of the tracking issue) and settle each
one (trade-off, position, open questions) before implementing; see [docs/adr/README.md](docs/adr/README.md).

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

- **ASCII only** in source and docs we author: no emoji, em-dashes/en-dashes (use `-`), smart quotes, or Unicode
  arrows/math symbols (write `<=`, `->`). This is about text we type, not a runtime constraint: data files (model
  rationales, manifests, the eval substrate) use `encoding="utf-8"` and pass non-ASCII through.
- Line length **120** for code (Ruff-enforced). For markdown prose it is a soft, by-hand target (`wrap = "keep"` means
  mdformat does not auto-wrap): a little over is fine; tables and links may exceed. **2-space indent** (not 4).
- Full type hints, new-style (`X | None`, never `Optional`).
- Ruff: all rules enabled; silence case by case **inline** with `# noqa: <code>` (such a line may exceed 120 - Ruff
  does not flag E501 on noqa lines, so the reason has room). Do not add global ignores to dodge findings; the only
  `lint.ignore` entries are Ruff's own unsatisfiable rule conflicts (D203/D213, COM812; see docs/adr/0009), plus the
  test relaxations already in per-file-ignores.
- Prefer fewer, larger, coherent files over many tiny ones.
- Public code first: within a file, put the public API at the top and private `_helpers` below the code that uses them.
- Docstrings: public (no leading underscore) functions, methods, and classes use reStructuredText (Sphinx) style
  (`:param:` / `:return:`, no `:type:` / `:rtype:`; type hints carry the types). Private (underscore) code may skip it;
  if present, keep it descriptive or Sphinx, never a different convention. Tests are exempt, but python-public test
  helpers/fixtures are not. See [development.md](development.md) for the rule and an example.
- Dependencies: minimal and MIT-compatible; avoid GPL. Add a dep only when first used.

## Tests

- pytest, with long descriptive test names.
- Mock the LLM endpoint; tests run offline and deterministically.

## Versioning

- 0.x for now: prefer clean design over backwards compatibility. Break the public API consciously and note how callers
  adapt.

## Working style

- Honesty over pleasing. No flattery. If a better approach exists, say so with reasons.
- Do not commit or push unless asked. Branch off `main`; never commit directly to `main`, and **never merge a PR to
  `main` yourself** - open it and leave the merge to a maintainer.
- Commit style (Conventional Commits for the commit that lands on `main`; encouraged but optional for individual
  commits) is documented in [development.md](development.md).
