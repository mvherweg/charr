# 0004. Use pydantic for models, config, and LLM response validation

- Status: Accepted
- Date: 2026-06-27

## Context

The dominant risk in the checker is whether a small local model returns JSON in the exact shape we asked for. We also
parse config from TOML, which benefits from validation and clear errors on typos. The project requires full type hints
and keeps dependencies minimal; `pydantic` was already named as the anticipated first runtime dependency in
[project.md](../../project.md).

## Decision

We will use **pydantic v2** for the domain models, the config models, and the `CheckResponse` schema returned by the
model. `CheckResponse.model_validate_json` parses and validates the model's reply in one step; config models use
`extra="forbid"` so unknown keys are caught rather than silently ignored.

Alternatives considered: dataclasses with hand-rolled validation (rejected: reinvents exactly what pydantic provides,
which is where the real risk lives); `TypedDict` (rejected: no runtime validation); attrs (rejected: still needs a
separate validation/serialization story).

## Consequences

- One-step parse-and-validate with precise errors when a 3-4B model returns malformed or off-schema JSON.
- Config typos fail loudly via `extra="forbid"`; the `exceptions` field is reserved with a lenient shape for later.
- `pydantic-core` is a compiled (Rust) wheel. That is fine for an application/CLI and is a single dependency, not a
  tree.
- A runtime dependency beyond the standard library, consistent with the project's stated plan.
