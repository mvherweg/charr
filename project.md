# Charr

> Working title. "Char" from **chart**, plus an extra **r** to make it unique. Not load-bearing, just memorable and
> evocative of "chart". (A possible future visual: a cartoony tank, *char* is French for tank, with a pirate shouting
> "arr!" riding a gun barrel that zig-zags like a line plot.)

## Overview

Charr is a **checker for charts**: a CLI tool that evaluates rendered chart **images** (PNG/JPEG) against a configurable
rule set, using **local LLMs**, and reports machine-readable (JSON) pass/fail results. It runs on demand, like running a
test suite over your charts, not as a live service.

## Problem and motivation

We produce a lot of data-analysis reports for high-level, often non-technical readers (up to C-level). The classic
structure applies: executive summary, then main findings, then details, and the reports contain **many charts**.

Everything else in an analysis is checkable. SQL, Python, and other code can be controlled for quality and correctness
with linters and static analysis. **Charts cannot.** Their output is an opaque artifact, a PNG/JPEG, not a text-readable
thing. Even tracing back to the generating code (Plotly, matplotlib, etc.) does not let you statically derive what the
chart will actually look like; that would require deep, reliable reasoning about the rendering.

So instead of reviewing the code, Charr evaluates the **output artifact directly**: it looks at the image. The checks
themselves are low-intelligence but genuinely necessary: *Is it simple? Does it have a title? Are the axes labeled? Are
there weirdly overlapping elements? Is text cleanly separated? Do the colors follow the specified palette? Is there a
legend when needed?*

## Vision: a three-step roadmap

1. **Big cloud LLM evaluates the image.** Roughly how this is done today. It works, but it is **expensive**.
   Reproducibility is a minor concern (not really an issue if the model is good enough) but worth keeping in mind. We
   want this reliable: not 100%, but good enough to depend on.
2. **[THIS ITERATION] Tuned for local LLMs.** Structure and tweak the approach so it runs **reliably on local models**,
   cutting cost. "Local" means **30B parameters or fewer** as the floor. We are hopeful it can go much smaller, down to
   **3-4B** (e.g. Ministral seems to do a decent job).
   - **4B is the success milestone:** under ~4B runs on essentially any PC, even without dedicated graphics (e.g.
     integrated Intel). Hitting this makes the project a great success.
   - **30B is the "minimum minimorum":** the largest model we would still consider acceptable.
   - Smaller than 4B would be a bonus.
3. **Purpose-built model (future).** Not possible today, but once we have accumulated enough data, we could train a
   dedicated model for specific checks, trained on the chart images and our rule sets, in the classical ML fashion. Out
   of scope for now.

## Core concept

Charr applies a **documented rule set** to chart images and reports, per chart, what passes and what fails. Rules can be
enabled, disabled, and configured.

It is **not live**. The run model is like a test run: a CLI invocation with the right parameters walks through your
charts/images and reports results for each. Think "point it at a folder of charts and get a verdict", not "an always-on
service".

> **A useful analogy: Ruff.** Some of Ruff's (the Python linter) concepts are a handy way to *picture* Charr: a
> documented, well-known rule set; choosing which checks to enable or disable; per-case exceptions. Treat it as a mental
> shortcut for explaining the shape of the tool.

## Scope of the first iteration

Build, in this repo, **two deliberately separate packages**:

1. **The chart checker (linter), CLI.** The primary deliverable: evaluate chart images against the rule set with a local
   LLM and emit JSON.
2. **The data generator.** A standalone, valuable-but-separate tool (see below). Kept apart on purpose: people who use
   the checker are not necessarily interested in evaluating or tuning its performance, so the two are not bundled.

**Explicitly deferred (not built now):**

- HTTP API and MCP interface. Kept in mind, trivial to add later on top of the core, but not in this iteration.
- The purpose-built/trained model (roadmap step 3).

## How it works

- **Input:** chart **images only** (PNG/JPEG), supplied as file paths, globs, or directories. Pure visual evaluation: no
  generating code, no required sidecar files.
- **LLM backend:** an **OpenAI-compatible HTTP endpoint** (`/chat/completions`). This works out of the box with Ollama,
  vLLM, LM Studio, and the llama.cpp server, and keeps Charr model- and runtime-agnostic.
- **Execution:** start by sending **all enabled rules in a single LLM call per image** (cheaper and faster). **This is
  an internal implementation detail and must not leak into the public API.** We may later learn there is a sensible max
  number of rules per call, or that certain rules only work well in isolation, and we want to change how the work is
  split *without* affecting users.
- **Output:** **JSON only** for now (machine-readable, friendly to agents and CI).
- **Exit code:** the CLI exits **non-zero when any enabled, non-excepted rule fails**, so it can gate CI and be driven
  by agents. The JSON report is still written to stdout.

## Rules

Charr ships a **built-in, documented catalog** of toggleable rules **and** supports **user-defined custom rules** from
day one.

**Initial built-in catalog:**

- **Has title:** the chart has a clear, present title.
- **Axes labeled:** axes carry labels where applicable.
- **No overlapping elements:** no weirdly overlapping/colliding text or elements; layout is readable.
- **Palette compliance:** colors match the configured/allowed palette.
- **Font compliance:** fonts match the configured expectation.
- **Axis units when not self-evident:** a numeric axis needs units; an axis that is obviously something else (e.g.
  dates) does not.
- **Legend when multiple groups:** a legend is present when more than one group/series is shown.
- **Zero-baseline when omitting it misleads:** the y-axis starts at 0 for plot types where not doing so is misleading
  (e.g. bar charts).
- **Background-series contrast:** the plot background contrasts clearly with every plotted data series, so no series
  blends into the canvas.

**Exceptions / opt-outs:** the global config is expected to make nearly everything pass as configured. For the few cases
that should be exempt, Charr provides an **exception mechanism**: per-rule / per-chart opt-outs. (Comparable to ignoring
a specific rule in a linter, analogy only.)

## Configuration

- **Sane defaults** out of the box; nearly everything is driven by config rather than per-run flags.
- **Format:** **TOML.** Read from `[tool.charr]` in `pyproject.toml` and/or a standalone `charr.toml`, discovered by
  walking **up** from the working directory (default search path).
- **Flags:** individual inputs can also be set on the command line, overriding config.
- **Credentials:** LLM credentials come from **environment variables**.

## Data generator (separate package)

A standalone package that produces **synthetic charts with ground-truth pass/fail labels per rule**. Its purpose is to
**benchmark and tune** the checker's accuracy: to measure how well a given (local) model performs against known-correct
labels, and to drive the push toward smaller models. Kept separate from the checker because evaluating/tuning
performance is a distinct use case from running the checks.

## Versioning and backwards compatibility

Charr is **version 0.x.y for the foreseeable future**. While we are on 0.x:

- **We do not chase backwards compatibility.** Prefer a clean, good-working design over preserving old behavior. If a
  better design means breaking the public API, take the better design.
- **Break consciously, not carelessly.** When we do change public API behavior, be deliberate about it: know what breaks
  and how callers should adapt, and note the change so users can follow it.

A stable-compatibility commitment is a later concern, for when (and if) we reach 1.0.

## Tech stack and conventions

- **Language:** Python **3.13+**.
- **Packaging / deps:** **uv** (Astral) for dependency and package management.
- **Tests:** **pytest**.
- **Linting:** **Ruff**, used strictly: enable **all** rules, then disable case by case **inline** with `# noqa`. Tests
  are the one exception: relax rules that don't fit them (notably the `assert` ban and public-method docstring
  requirements). Prefer **long, clearly descriptive test names**.
- **Style:** line length **120** for code and markdown alike (wrap markdown prose too; only exceed where a single link
  or token makes it impractical); **2-space indent** (explicitly *not* 4).
- **Encoding:** **ASCII only** in all markdown and code. No em-dashes or en-dashes (use a plain hyphen), no
  emoticons/emoji, no smart quotes, no Unicode arrows or math symbols (write `<=`, `->`).
- **Typing:** type hints **everywhere**, new-style only, e.g. `X | None`, never `Optional`.
- **Dependencies:** keep them **minimal**, only big, high-value ones. Likely candidates: `pydantic` (LLM-structured
  output); a minimal web framework such as `bottle`/`flask` *if/when* an HTTP API is added; possibly `requests`. Not
  exhaustive; resist pulling in extras.
- **File structure:** prefer **fewer, larger, coherent files** over scattering 50-100 tiny ones. Split only with good
  motivation (concepts that genuinely belong apart). Extracting from a big file later is easy; merging small files back
  is harder.

## Licensing

**License: MIT** (see `LICENSE`). Every dependency must therefore be MIT-compatible: Apache-2.0 is generally fine;
**verify** before pulling anything in. **Avoid GPL**: be careful not to contaminate the project with it.

## Ways of working

- **Review flow:** when a review comes in, address **every** point, either act on it and resolve as suggested, or reply
  on the thread explaining why not. There is **no second automated round**. After that, alert the human for review; they
  either come back with points to discuss or merge (item done).
- **Honesty over pleasing.** No flattery, no empty compliments. If a proposed idea is good but there is a clearly better
  one, say so directly and give the reasons; don't just agree.

## Open questions and future ideas

- How far down can we shrink the model while staying reliable (3-4B and below)?
- Adding an HTTP API and/or MCP interface on top of the core.
- Training a purpose-built model once enough labeled data exists (roadmap step 3).
- Branding / mascot direction for the "Charr" name.
