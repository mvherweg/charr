# Charr

A checker for charts: lint rendered chart images (PNG/JPEG) against a configurable rule set using (local) LLMs, run from
the command line.

> Status: early scaffold, version 0.x. Not yet functional; the CLIs are placeholders.

## Why

Charts are the one part of a data-analysis report you cannot check with ordinary static analysis: the output is an
image, not text. Charr evaluates the rendered image directly against a documented rule set (has-title, axes-labeled,
palette compliance, and so on) and reports machine-readable pass/fail results.

## Documentation

- [project.md](project.md) - what Charr is, the vision, scope, and the decisions behind it.
- [development.md](development.md) - setup, repository layout, and development workflow.

## Layout

This repo is a uv workspace with two separate packages:

- `packages/charr` - the chart checker (CLI), the primary deliverable.
- `packages/charr-datagen` - the data generator: synthetic charts with ground-truth labels for benchmarking the checker.

## License

MIT. See [LICENSE](LICENSE).

## Contributing

This is a personal project and is not open to external contributions or issues. See [CONTRIBUTING.md](CONTRIBUTING.md).
