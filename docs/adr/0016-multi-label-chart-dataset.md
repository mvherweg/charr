# 0016. The labeled-chart dataset is multi-label: a chart may violate several rules

- Status: Accepted
- Date: 2026-06-28

## Context

Every chart is labeled against all rules (the manifest is a full per-rule verdict vector). That leaves a foundational
modeling question: is a labeled chart a **single-label** instance (one issue per chart, like single-class
classification) or **multi-label** (a chart may violate several rules at once)?

Real charts often carry several issues simultaneously. A chart combining issues may be harder for the checker than one
with a single issue, and that hardness is worth measuring. More pointedly, a dataset built on at-most-one-issue charts
would bias anything trained or tuned on it toward an unrealistic single-problem world, harming quality. Against that,
modeling the dataset as multi-label costs more in construction and complicates allocation - an image becomes a vector of
conditions, not a single cell.

## Decision

We model the labeled-chart dataset as **multi-label**: a chart may exhibit multiple simultaneous rule violations, and
the manifest records the full verdict vector. That is the design commitment.

As a purely temporary scope limit, the MVP generator produces **at most one intended issue per chart** (the remaining
rules deliberately held to pass / NA). This is a sequencing choice, not the model - single-issue instances are just the
degenerate case of a multi-label dataset, the manifest is already a vector either way - and it is tracked in
[issue #3](https://github.com/mvherweg/charr/issues/3).

Lifting that scope limit will **refine ADR-0014's allocation**: with a vector as the unit, allocation must guarantee
per-rule polarity coverage **and** coverage of meaningful combinations, keeping ADR-0014's stratified-over-i.i.d.
principle while changing its mechanics.

Alternatives considered:

- **Single-label model (permanently one issue per chart):** rejected. It biases the dataset toward an unrealistic
  single-problem world, hides combination-hardness from measurement, and would mistrain anything tuned on it.
- **Multi-issue generation already in the MVP (no deferral):** the model demands it eventually, but generating several
  controlled issues per chart complicates construction and allocation, so the MVP ships single-issue instances first and
  issue #3 lifts the restriction. This is a scheduling choice that lives in the issue, not a competing model.

## Consequences

- The manifest and eval are multi-label throughout: metrics aggregate per rule across all images regardless of how many
  issues each image carries, so nothing in the model changes when multi-issue generation lands.
- The single-issue MVP is understood as the degenerate case of the model - a way station, not a destination - so a
  future contributor will not mistake it for an intended single-label commitment.
- ADR-0014's allocation mechanics will be revisited when issue #3 lands; until then they are correct for single-issue
  instances.
