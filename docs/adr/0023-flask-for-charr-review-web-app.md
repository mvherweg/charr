# 0023. Flask for the `charr-review` web app

- Status: Accepted
- Date: 2026-06-30

## Context

The review front-end ([ADR-0022](0022-charr-review-package-and-substrate-contract.md)) is a local, single-page web app:
the chart is an image, the per-rule expected/predicted/rationale view is tabular, and navigation must feel instant. The
form factor (a browser SPA over a small local server, rather than a native desktop window or a terminal UI) is settled -
images and tables render poorly in a TUI, and a native toolkit makes filterable tables and crisp image scaling harder.
What remains is the server: how the localhost backend serves one JSON payload, the chart images, and the static assets.

The forces:

- The backend's job is tiny: hand the browser the whole (small, text) substrate as JSON once, then serve images on
  demand with cache headers while the client does all navigation, filtering, and prefetching. A handful of routes.
- The repo leans on the standard library and minimal dependencies ([ADR-0002](0002-requests-not-httpx-or-openai-sdk.md)
  chose `requests` over heavier stacks). So a new dependency has to earn its place.
- The alternatives are stdlib `http.server` (zero new deps, but low-level: manual routing, content-type and cache
  headers by hand, threading care) or a micro-framework.

## Decision

We will use **Flask** for the `charr-review` backend.

Flask is small, ubiquitous, and MIT-licensed; its routing, static-file serving, and `send_file` (with conditional /
range support) remove exactly the boilerplate the stdlib option makes us write and maintain by hand. The dependency is
effectively no-cost: it is a well-established part of the ecosystem and is the natural building block if Charr later
grows any other HTTP surface (for example a hosted checker API), so we expect to reuse it rather than carry it for one
tool.

Alternatives considered and why they lost:

- **Stdlib `http.server` (`ThreadingHTTPServer` + a `BaseHTTPRequestHandler`).** Zero new dependencies, but the
  low-level handler (manual routing, MIME and cache headers, threading) is avoidable complexity to own for a UI that
  should stay thin; the saved dependency is not worth the hand-rolled plumbing.
- **A heavier async stack (FastAPI + uvicorn / Starlette).** More machinery and more transitive dependencies than a
  read-only local viewer justifies; its strengths (async, schema-driven APIs) do not apply here.
- **No server - a self-contained static HTML report.** Tempting for having no runtime, but avoiding a server means
  base64-inlining every chart into one multi-megabyte file, which defeats the "instant" goal and prevents lazy,
  on-demand image loading. A server that streams images as requested scales far better.

`charr-review` therefore depends on `charr`, `flask`, and `pydantic`; Flask is the first web dependency in the
workspace.

## Consequences

- Easier: the backend stays a few short route handlers; serving static assets and images (with correct content types and
  caching) is handled by the framework, so effort goes into the data shaping and the front-end where it matters.
- Harder, knowingly accepted: Flask (and Werkzeug/Jinja/Click underneath it) is the first non-stdlib web dependency in
  the repo, a small step away from the stdlib-first stance of ADR-0002. We accept it because the cost is low and the
  reuse likely.
- Revisit when: Charr gains a real hosted/networked service with concurrency or async needs that outgrow a synchronous
  local dev server - at that point reassess the framework for that service rather than retrofitting this local tool.
