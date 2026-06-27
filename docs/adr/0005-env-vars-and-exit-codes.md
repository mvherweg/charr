# 0005. Credentials via environment variables; three-way exit codes

- Status: Accepted
- Date: 2026-06-27

## Context

The checker must keep LLM credentials out of the repo and out of config files, and it must be usable as a CI gate and by
agents. [project.md](../../project.md) mandates credentials from environment variables and a non-zero exit on failure,
but leaves the exact variable names "proposed" and does not pin the exit-code scheme. A driver needs to tell apart "the
charts failed the rules" from "the tool could not run", because those warrant different reactions.

## Decision

Credentials and endpoint come from environment variables: `CHARR_LLM_BASE_URL` (required), `CHARR_LLM_MODEL` (required),
and `CHARR_LLM_API_KEY` (optional; local servers often need none). `base_url` points at the API root including any
version prefix (e.g. `http://localhost:11434/v1`); `/chat/completions` is appended.

Exit codes:

- `0`: ran with no enabled, non-excepted rule failing.
- `1`: ran; at least one rule failed (the CI gate).
- `2`: could not run (missing/invalid credentials, no inputs matched, malformed config, or a backend/LLM failure).

Alternatives considered: a single non-zero code (rejected: cannot distinguish "charts failed" from "tool broke");
reading credentials from the config file (rejected: invites secrets into the repo).

## Consequences

- Agents and CI can branch on failure (`1`) versus malfunction (`2`).
- Secrets stay out of version control and out of TOML.
- Three environment variables to set before a real run.
- The `1` vs `2` split and the variable names are now a public contract. While on 0.x they can still change, but
  consciously and noted (see [project.md](../../project.md) on versioning).
