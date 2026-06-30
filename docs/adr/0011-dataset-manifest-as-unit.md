# 0011. The dataset unit is a manifest, not an enforced directory

- Status: Accepted
- Date: 2026-06-28

## Context

[ADR-0010](0010-three-packages-eval-drives-charr.md) made the dataset format a published contract that `charr-eval`
consumes and that must be hand-authorable and tool-agnostic (orgs build private datasets from human-reviewed production
cases). This ADR fixes the **structural model**: how a labeled dataset is laid out and what `charr-eval` is pointed at.

The forces:

- **Humans curate incrementally.** A reviewer adds one flagged chart at a time. Constantly creating files is more
  onerous than adding lines to one file.
- **A test set spans several groupings.** Real reasons to keep them apart: ordinary org friction (bringing them together
  is just inconvenient), the distinction between a generated set and a manually grown one, and thematic splits. The
  latter two warrant per-grouping identity and want to be a reported dimension, not just a union convenience.
- **Provenance can be light.** A grouping's own identity (its name/path) is enough for now; no metadata block needed.
- **Splits and re-labelings should not duplicate images.** A thematic subset, or a second reviewer's labels, should not
  require copying image files.

An earlier framing made a "location" a directory that *owns* its images. But the code never needs that: it reads a
labels file, resolves each image path relative to that file, runs, and attributes results back to it. Whether the images
sit under that file's directory is a convention the code never checks - so enforcing it buys nothing and blocks the
shared-image-pool cases above.

## Decision

The dataset unit is a **manifest**: a single file mapping images to per-rule verdicts, with image paths resolved
relative to the manifest's own directory. We will not enforce that referenced images live under that directory; staying
within it is a recommended convention for self-containment, nothing more.

- A **test set** is one or more manifests, unioned. Records are keyed by `(manifest, image-path)`, so two manifests that
  reference the same image stay distinct data points.
- Results are **reported per manifest**, each identified by a display name of the manifest's parent directory plus its
  filename stem (so a report reads `config-00/labels: ...`). Parent-plus-stem rather than the bare stem keeps datasets
  that all use the conventional `labels.jsonl` filename distinct in the report; it is a readable label, not a full path,
  so it points at the dataset's directory without claiming to encode its complete provenance.
- Image paths are relative to the manifest and may include subdirectories (and, by the no-enforcement rule, may point
  outside the manifest's tree).

The manifest's on-disk encoding is decided separately in [ADR-0012](0012-manifest-encoding-jsonl.md).

Alternatives considered:

- **Per-image sidecars** (`chart.png` + a labels file beside each): rejected. File proliferation, no single overview, no
  home for grouping-level identity, and worse for human curators who would rather append lines than spawn files.
- **One global manifest** for the whole set: rejected. Onerous for large sets, combining sets means merging files rather
  than listing them, and it does not model the several-groupings reality.
- **Enforced "location = directory that owns its images":** rejected. The code does not need containment, and enforcing
  it forces image duplication for thematic splits and re-labelings instead of letting multiple manifests reference one
  shared image pool.

## Consequences

- Thematic splits and re-labelings are just additional manifests over a shared image pool - no image duplication.
- Per-manifest reporting gives orgs the generated-vs-manual and thematic breakdowns they want, and run provenance is
  simply the manifest's path; no metadata block to design now.
- Union keys by `(manifest, image-path)`, so overlapping references across manifests are distinct evaluations; a
  deliberately duplicated reference is double-counted, transparently and by the author's choice.
- Portability is a convention, not a guarantee: a manifest that references images via `../` is not self-contained if
  moved alone. We accept this and recommend keeping images under the manifest when self-containment matters.
- "Location" is dropped in favor of "manifest" everywhere (the issue's wording is updated to match); this is a clearer
  term for the same decision, not a reversal.
- This would be revisited if grouping-level metadata beyond a name became necessary, or if a single-file dataset proved
  to be the dominant shape after all.
