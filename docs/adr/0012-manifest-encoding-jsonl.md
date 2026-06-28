# 0012. Encode the labels manifest as JSONL, not TOML or a single JSON document

- Status: Accepted
- Date: 2026-06-28

## Context

[ADR-0011](0011-dataset-manifest-as-unit.md) defines a manifest as a file of per-image records (image -> per-rule
verdicts). This ADR picks its on-disk encoding, the explicit JSON(L)-vs-TOML trade-off deferred earlier.

The forces:

- **Homogeneous, growing records.** One record per image; a real set has many, and they all share a shape.
- **Incremental human curation.** Adding a reviewed case should be cheap - ideally append, not restructure.
- **Tool-agnostic and programmatic.** Both `charr-datagen` and external pipelines must emit it easily, and humans must
  be able to read and hand-edit it.
- **Fits the existing stack.** Charr already models with pydantic ([ADR-0004](0004-pydantic-for-models-and-validation.md))
  and speaks JSON to the LLM ([ADR-0008](0008-json-schema-response-format.md)); JSON is the path of least resistance for
  validation and reuse of `Verdict` / `RuleId`.

## Decision

We will encode a manifest as **JSONL**: one JSON object per line, one line per image record. Blank lines are skipped;
each non-blank line validates against a pydantic record model that reuses charr's `Verdict` and `RuleId`.

Alternatives considered:

- **TOML:** friendlier for a small, hand-tuned config file, but a manifest is many homogeneous records, which TOML
  expresses as verbose array-of-tables. Adding a case means extending a table rather than appending a line, and it is
  awkward to emit programmatically at scale. Good for config, wrong shape for a record log.
- **A single JSON document (one array):** keeps JSON's ubiquity but must be parsed and rewritten as a whole to append,
  is not streamable, and holds the entire set in memory. JSONL keeps every JSON benefit while being append- and
  stream-friendly and line-diffable.

## Consequences

- Adding one reviewed case is appending one line - the curation ergonomics ADR-0011's forces asked for.
- Streamable and memory-friendly for large sets; line-diffable, so changes read cleanly in code review.
- Each line maps directly onto a pydantic record, reusing charr's verdict types, so validation is uniform with the rest
  of the codebase.
- Cost: it is not one pretty document a human eyeballs whole; a line per image stays readable, and standard tooling
  handles JSONL, so we accept this.
- JSONL has no natural place for a per-manifest header. ADR-0011 keeps provenance light (the manifest's path), so none
  is needed now; if light metadata is ever wanted, a leading header record or a sibling file is the likely route - noted,
  not decided here.
