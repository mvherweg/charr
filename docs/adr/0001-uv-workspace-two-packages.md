# 0001. uv workspace with two separate packages

- Status: Accepted
- Date: 2026-06-27

## Context

Charr ships two things: the chart checker (the primary deliverable) and a data generator that produces synthetic charts
with ground-truth labels for benchmarking the checker. They serve different audiences: someone running the checker in CI
does not necessarily want the generator's dependencies, and vice versa. They also evolve independently. At the same time
we want one repo with shared dev tooling (one Ruff/pyright/pytest config, one lockfile) so the two stay consistent.

This ADR ratifies the structure established in [project.md](../../project.md) and
[development.md](../../development.md).

## Decision

We will use a single repo managed as a **uv workspace** with two members under `packages/`: `charr` (the checker CLI)
and `charr-datagen` (the generator). Each has its own `pyproject.toml` and its own runtime dependencies. The workspace
root holds the shared dev-dependency group and all tool configuration.

Alternatives considered: a single package exposing the generator behind optional extras (rejected: bundles unrelated
deps and blurs two genuinely separate use cases); two unrelated repos (rejected: loses shared tooling and a single
lockfile, and makes coordinated changes harder).

## Consequences

- Users install only the package they need; the checker stays lean.
- One place for lint/type/test config keeps both packages honest; CI runs the whole workspace.
- Two `pyproject.toml` files to maintain.
- The packages are independent on purpose: sharing code between them requires a real, declared dependency rather than a
  casual import. If they ever need to share a meaningful core, that is a new decision (likely a third package).
