# 0008. Request structured output via json_schema, not json_object

- Status: Accepted
- Date: 2026-06-28

## Context

The checker asks the model to return JSON matching `CheckResponse`. The first implementation sent
`response_format: {"type": "json_object"}`. A real trial against an LM Studio endpoint rejected this with HTTP 400:
`'response_format.type' must be 'json_schema' or 'text'`. So `json_object` is not universally accepted across
OpenAI-compatible backends, even though OpenAI and Ollama take it.

The 400 was also opaque: the client surfaced only the status line and dropped the response body, so the reason was
invisible until probed by hand.

## Decision

Send `response_format` as **`json_schema`** (structured outputs), built from the model's own schema:

```
{"type": "json_schema", "json_schema": {"name": "charr_report", "schema": CheckResponse.model_json_schema()}}
```

`strict` is omitted for lenient local-backend compatibility. This is the format LM Studio requires and is also supported
by OpenAI, Ollama, vLLM, and the llama.cpp server; it additionally constrains the model to our exact shape, which helps
small models. Verified end to end against `qwen/qwen3-vl-4b` and `mistralai/ministral-3-3b`.

Alongside this, the client now includes the backend's response body (truncated) in `LlmError` on an HTTP error, so a
rejected request explains itself.

Alternatives considered: keep `json_object` (rejected: LM Studio refuses it, and it is the less reliable mode);
`text` plus prompt-only JSON instructions (rejected: least reliable, no schema constraint); make `response_format`
configurable per backend (deferred: `json_schema` covers the targets; revisit if a backend appears that lacks it).

## Consequences

- The checker works against LM Studio out of the box, and remains compatible with the other OpenAI-compatible backends.
- The request schema stays in sync with `CheckResponse` automatically (one source of truth).
- Backend errors are now actionable rather than an opaque status line.
- A backend that supports neither `json_schema` nor our needs would require a future `response_format` config knob (new
  ADR).
