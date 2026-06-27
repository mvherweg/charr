# 0002. Use `requests` for the LLM call, not httpx or the openai SDK

- Status: Accepted
- Date: 2026-06-27

## Context

The checker makes one OpenAI-compatible `POST /chat/completions` (vision) request per image. The target backends are
local servers: Ollama, vLLM, LM Studio, and the llama.cpp server, where the API key is often empty and behaviors vary
slightly from the OpenAI cloud. Constraints: dependencies must be minimal and MIT-compatible; tests must run offline and
deterministically. The HTTP call is already hidden behind an `LlmClient` Protocol, so nearly all tests use a plain fake
client and never touch HTTP at all; only the one concrete client needs an HTTP test seam.

## Decision

We will use **`requests`** (Apache-2.0) for the single POST and own the request/response shape ourselves. We add
`types-requests` as a dev-only stub so pyright stays clean. The concrete client takes an injected `requests.Session`, so
tests inject a fake session.

Alternatives considered:

- **openai SDK**: a large surface for one POST, drags in its own httpx + pydantic, and assumes OpenAI-cloud behaviors
  (always-on auth, retries, model listing) we would fight against local servers. Rejected.
- **httpx**: modern, with a built-in `MockTransport` and an async path. Its advantages are real but do not clear the
  "meaningful gain" bar here, because the `LlmClient` Protocol already isolates HTTP and our needs are one sync call.
  Rejected for now.
- **stdlib `urllib`**: zero deps, but hand-rolled JSON, timeouts, and error handling against flaky local servers.
  Rejected as fragile boilerplate.

## Consequences

- Tiny, well-understood surface; we fully control the payload and parsing, which suits the OpenAI-compatible contract.
- Tests inject a fake `Session`; no network, fully deterministic.
- `requests` is synchronous: parallelism across images, when added, uses a thread pool rather than async.
- We carry a `types-requests` dev stub and hand-maintain the request body shape (an acceptable, stable contract).
- Revisit if we need high-fan-out async I/O; httpx would then be the natural successor (new ADR).
