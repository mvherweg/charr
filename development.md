# Development

How to set up, build, run, and contribute to Charr. For what Charr is and why, see [project.md](project.md).

> Status: the repository is being scaffolded. Commands and paths marked "(proposed)" describe the target setup and may
> not exist yet.

## Conventions at a glance

- **ASCII only** in all markdown and code. No em-dashes or en-dashes (plain hyphen instead), no emoji, no smart quotes,
  no Unicode arrows or math symbols (write `<=`, `->`).
- **Python 3.13+**, full new-style type hints (`X | None`, never `Optional`).
- **uv** (Astral) for everything: environments, dependencies, running tools.
- **Ruff** strict: all rules on, disabled case by case inline with `# noqa` (such a line may exceed 120 - Ruff does
  not flag E501 on `# noqa` lines, leaving room for the reason).
- **pyright** for type checking; everything is fully type-hinted.
- **pytest** for tests, with long descriptive test names.
- Line length **120** for code (Ruff-enforced). For markdown prose it is a soft, by-hand target (`wrap = "keep"` means
  mdformat does not auto-wrap): a little over is fine, and tables/links may exceed. **2-space indent** (not 4).
- Prefer **fewer, larger, coherent files** over many tiny ones.
- **Public code first:** within a file, put the public API (entry points, the functions/classes callers use) at the top
  and private `_helpers` below the code that uses them. The top of the file is the natural place to start reading. Safe
  in Python since module-level names resolve at call time, so a public function may call a `_helper` defined lower.
- **Docstrings:** public (no leading underscore) functions, methods, and classes use reStructuredText (Sphinx) style -
  `:param:` / `:return:`, no `:type:` / `:rtype:` (type hints carry the types). Private (underscore) code may skip it.
  Tests are exempt, but public test helpers/fixtures are not. See [Docstrings](#docstrings).
- **Pre-1.0 (0.x):** clean design beats backwards compatibility. Break the public API when it makes the design better,
  but do it consciously and note how callers adapt.

## Docstrings

Public functions, methods, and classes - "public" meaning the Python convention of no leading underscore - use
reStructuredText (Sphinx) docstrings: a one-line imperative summary, a blank line, then a `:param <name>:` for each
argument and a `:return:` for the result. Omit a field when there is nothing to document (no arguments, or the function
returns `None`); add `:raises <Error>:` where raising is part of the contract. Do not use `:type:` or `:rtype:` - the
type hints carry the types.

```
def add_absolutes(number_one: int, number_two: int) -> int:
  """Add the absolute values of two integers.

  :param number_one: First number in the addition.
  :param number_two: Second number in the addition.
  :return: The sum of the absolute values of both numbers.
  """
  return abs(number_one) + abs(number_two)
```

Private (underscore-prefixed) functions, methods, and classes do not need a docstring. If one is present it may be plain
descriptive prose or the same Sphinx style, but it must not introduce a different convention (no Google or NumPy style).
Data-model classes (e.g. pydantic models) may keep a descriptive class docstring rather than documenting each field.

Tests are exempt: a `test_*` function is documented by its long descriptive name, not a docstring. Test *helpers* are
not exempt - a python-public (non-underscore) helper or fixture built for tests follows the same Sphinx rule, while
underscore-prefixed test helpers do not.

## Prerequisites

- **uv** (the Astral tool). Install per https://docs.astral.sh/uv/. uv manages the Python toolchain too, so you do not
  need a separate Python install.
- **A local, OpenAI-compatible LLM endpoint** for running and testing the checker against real models. Any of these
  expose an OpenAI-compatible `/chat/completions` API:
  - Ollama (`ollama serve`), LM Studio, vLLM, or the llama.cpp server.
  - Use a **vision-capable** model, since Charr evaluates images. Prefer a small one (3-4B) during development to match
    the project's target.

## Repository layout (proposed)

Charr is a single repo holding **two separate packages**, managed as a uv workspace so they share dev tooling but stay
independent:

```
Charr/
  pyproject.toml            # uv workspace root + shared dev deps and tool config
  packages/
    charr/                  # the chart checker (CLI) - primary deliverable
      pyproject.toml
      src/charr/
      tests/
    charr-datagen/          # the data generator - synthetic labeled charts (depends on charr)
      pyproject.toml
      src/charr_datagen/
      tests/
    charr-eval/             # the evaluator - scores the checker against a labeled dataset (depends on charr)
      pyproject.toml
      src/charr_eval/
      tests/
  project.md
  development.md
  docs/adr/                 # Architecture Decision Records (committed; the "why" trace)
  dev-recs/                 # source recordings + transcripts (not shipped)
```

The packages are kept apart on purpose (docs/adr/0010): a user of the checker is not necessarily interested in
generating data or scoring runs. `charr-datagen` and `charr-eval` both depend on `charr` (for the shared rule catalog
and verdict vocabulary) but never on each other, so the evaluator can score any dataset in the manifest format,
generated or hand-curated.

## Extending the generator (charr-datagen)

The generator is a registry of data (see [docs/adr/0018](docs/adr/0018-generator-structure-recipe-registry.md) and
[0019-0021](docs/adr/README.md) for the why; fuller docs are tracked in issue #9). The one rule that keeps ground-truth
labels correct: a knob is either **label-bearing** (it changes a verdict) and is controlled, or **label-neutral**
(subject vocabulary, numbers, which palette colour/approved font a compliant chart uses, grid, marker, series count) and
is randomized freely from the seeded RNG. Never randomize a label-bearing knob.

Palette and font are label-bearing only *relative to a declared expectation*. That expectation is a **style-config**: a
run samples N independent `(palette, approved-fonts)` configs (`configs.py`) and writes one self-describing dataset per
config under `out_dir/config-NN/`, each with its own `charr.toml`. The recipe draws a *compliant* chart's colours from
the config palette and its font from the approved set, and draws each *violation* outside the config - a colour beyond
`T_VIOLATION` of the palette in CIEDE2000 (`colour.py`), or a font differing by a distinguishing property from every
approved font (`fonts.py`). So the label stays exact for any sampled config.

- **Add subject variety:** append a `Domain` literal to `DOMAINS` in `domains.py`. Domains are pure label-neutral
  vocabulary, so the weirder the better (see `improbable`, `mundane-absurd`).
- **Add a chart type:** append a `ChartType` to `REGISTRY` in `recipes.py` with a compliant-`baseline` builder, its
  `na_rules` (rules structurally impossible for it), `supports_single_group`, and - rarely - any type-specific
  `extra_defects` (the eight built-in rules are all covered by the shared `GLOBAL_DEFECTS`, so this is usually empty).
- **Add a font:** bundle the `.ttf` under `charr_datagen/fonts/` (OFL/Apache; record it in `fonts/LICENSES/NOTICE.md`)
  and append a `Font` to `SUPPORTED_FONTS` in `fonts.py` with its distinguishing properties (`serifs`/`monospaced`/
  `script`). Keep the supported set mutually distinct: a violation is any supported font in a *different* bucket, so two
  fonts that share all three properties are siblings (compliant variety only), never a violation pair.
- **Tune the style space:** the palette/font-count ranges live in `configs.py`; the colour distinctness thresholds and
  the legible band live in `colour.py` (calibrated as CIEDE2000 JND multiples - re-check the density/retry test if you
  change them).

The generic tests in `tests/test_recipes.py` then validate the addition automatically: `capable_types` proves every
`(rule, polarity)` cell stays servable (pure metadata, no seed), and the label tests prove each `(cell, type)` is
correct and invariant across seeds and sampled configs. `tests/test_fonts.py` proves the supported set always leaves a
distinct violation. If you add a rule and no chart type can serve one of its cells, the coverage test fails with a
precise message - run `uv run pytest packages/charr-datagen` after any change here.

## Decisions (ADRs)

Non-obvious design choices are recorded as Architecture Decision Records under [docs/adr/](docs/adr/README.md): one
decision per file, with its context, the alternatives, and the consequences we accepted. Read them for "why is it this
way"; this file and [AGENTS.md](AGENTS.md) hold the always-on conventions. When you make a design choice with real
alternatives, copy `docs/adr/0000-template.md` to the next number and add it to the index.

## Setup

```
# from the repo root: create the venv and install all workspace members + dev deps
uv sync
```

`uv run <cmd>` runs a command inside the project environment without activating it manually.

## Running the tools

```
# run the chart checker over a folder of images (non-recursive), JSON on stdout
uv run charr check ./charts

# point at single files or a simple glob too (no ** recursion yet)
uv run charr check report.png "charts/*.png"

# generate a multi-config dataset sweep (one self-describing config-NN/ dataset per style-config)
uv run charr-datagen generate --out ./set --configs 4 --samples 60 --seed 0

# score the checker across every config's manifest (unioned; needs CHARR_LLM_* set; manual/dev use)
uv run charr-eval ./set/*/labels.jsonl
```

The checker prints **JSON only** and exits **non-zero when any enabled, non-excepted rule fails** (1 = a rule failed,
2 = could not run), so it can gate CI or be driven by an agent.

## Configuration and credentials

- **Config file:** TOML. The checker reads `[tool.charr]` from `pyproject.toml` and/or a standalone `charr.toml`,
  discovered by walking **up** from the working directory. CLI flags override config.
- **Credentials and endpoint:** LLM settings come from **environment variables**: `CHARR_LLM_BASE_URL` (the API root,
  including any version prefix, e.g. `http://localhost:11434/v1`), `CHARR_LLM_MODEL`, and the optional
  `CHARR_LLM_API_KEY`. Keep keys out of the repo and out of config files.

A minimal `charr.toml` might look like (illustrative):

```
[tool.charr]
# select which built-in rules are active, configure palette/fonts, etc.
# per-rule / per-chart exceptions go here as the opt-out mechanism
```

## Linting and formatting

```
uv run ruff check .          # lint
uv run ruff check --fix .     # lint + autofix where safe
uv run ruff format .          # format
```

Policy: **enable all Ruff rules**, then silence on a case-by-case basis **inline** with `# noqa: <code>` (with a reason
where it helps), rather than broadly disabling rules in config. The one global `lint.ignore` holds only Ruff's own
unsatisfiable rule conflicts (the discarded half of `D203`/`D211` and `D212`/`D213`, plus `COM812`, which conflicts with
the formatter); see [docs/adr/0009](docs/adr/0009-resolve-ruff-rule-conflicts-in-config.md). It is not for dodging
findings.

Tests are the one place rules are relaxed: notably the ban on `assert` (asserts are how pytest works) and the
public-method docstring requirement. Configure those relaxations scoped to the tests path.

## Markdown

Markdown is formatted with mdformat (config in `.mdformat.toml`: `wrap = "keep"`, sequential list numbering). With
`wrap = "keep"`, mdformat does not reflow prose, so editing a sentence no longer rewraps the whole paragraph; wrap
prose by hand, aiming for 120 (see [docs/adr/0007](docs/adr/0007-markdown-wrap-keep.md)). 120 is a soft target to
limit horizontal scrolling and match our code width, not a hard rule: a little over is fine, and unbreakable content
(tables, long links) may exceed it. GFM pipe tables are supported
via the `mdformat-tables` plugin (a dev dependency, auto-discovered by mdformat); without it mdformat would reflow a
table into prose, so keep the plugin in the dev group (see [docs/adr/0006](docs/adr/0006-mdformat-tables-for-gfm-tables.md)).

```
uv run mdformat $(git ls-files '*.md')           # format in place
uv run mdformat --check $(git ls-files '*.md')    # verify only (CI uses this)
```

## Type checking

Everything is fully type-hinted (new-style). Check types with:

```
uv run pyright
```

## Testing

```
uv run pytest                 # run everything
uv run pytest packages/charr  # one package
```

- Use **long, clearly descriptive test names** that read as a sentence about the behavior under test.
- Keep tests deterministic. Where a test would otherwise hit a real LLM endpoint, stub/mock the backend so the suite
  runs offline and fast; reserve real-model runs for `charr-eval` against a generated dataset.

## Checks and CI

There are no forced local hooks (no pre-commit, no pre-push). Run checks locally whenever useful, in any subset, for
maximum flexibility. The gate is the pull request: CI runs the full set on every push to the PR, and the latest commit
must be green.

CI (GitHub Actions, `.github/workflows/ci.yml`) runs, after `uv sync`:

- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run pyright`
- `uv run mdformat --check $(git ls-files '*.md')`
- `uv run pytest`
- an ASCII-only check over tracked `*.py` and `*.md` files

## Commits and merges

- Work on a feature branch and open a pull request; **never commit to `main` directly, and never merge a PR yourself** -
  a maintainer does the merge (agents in particular must not merge themselves).
- The commit that lands a PR on `main` (merge or squash) uses
  [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): a `feat:` / `fix:` / `docs:` / ... type, an
  imperative summary, an optional body, and a `BREAKING CHANGE:` footer when the public API breaks.
- Individual commits along the way are **encouraged** to follow the same style but are **not required** - keep them
  lightweight and flexible while you work. The landing commit is the one that has to read well.

## Dependencies

- Add deps with uv, scoped to the package that needs them:

```
uv add <pkg>                  # runtime dep (run inside the target package, or use --package)
uv add --dev <pkg>            # dev-only dep
```

- Keep the dependency set **minimal**: only big, high-value libraries. Likely runtime candidates are `pydantic`
  (structured LLM output) and, only if/when an HTTP API is added, a minimal web framework (`bottle`/`flask`); possibly
  `requests`.
- **License check before adding:** the project is MIT-licensed, so every dependency must be MIT-compatible. Apache-2.0
  is generally fine. **Avoid GPL** to prevent contaminating the project; verify before pulling anything in.

## Contribution flow

1. Branch off `main` (do not commit directly to `main`).
2. Implement the change. Match the surrounding code and the conventions above.
3. Open a pull request. Running the checks locally first is encouraged but optional (see Checks and CI); CI runs the
   full set on the PR and is the gate.

**Handling a review:**

- A new PR automatically gets a **GitHub Copilot review** (via a repository ruleset). Triage it: fix the points you
  judge valid, and reply on the thread to the ones you judge invalid, explaining why. Copilot reviews **once per PR** -
  it is not re-triaged on later pushes.
- Address **every** review point (Copilot or human): either act on it and resolve as suggested, or reply on the thread
  explaining why you believe it should not be done.
- Every new commit pushed to the PR re-runs CI; confirm it is green again on the new head commit before handing back.
- There is **no second automated round**. Once all points are addressed, alert the human reviewer.
- The human then reviews and either comes back with additional points to discuss, or merges (at which point the item is
  done).

**Working style:** honesty over pleasing. No flattery or empty agreement. If a proposed idea is good but a clearly
better one exists, say so directly and give the reasons.
