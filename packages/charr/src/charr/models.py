"""Core domain vocabulary for the Charr checker.

These models are the shared language used across the package: the rule catalog, the per-rule verdicts a model
returns, and the aggregated report rendered to stdout. The module is deliberately free of I/O, HTTP, and LLM concerns so
it can be imported anywhere without side effects.
"""

import json
from enum import StrEnum

from pydantic import BaseModel, computed_field

type RuleId = str
"""Stable, kebab-case identifier for a rule, e.g. ``has-title``."""


class CharrError(Exception):
  """Base for errors meaning Charr could not run (bad config, no inputs, LLM failure); the CLI maps these to exit 2."""


# The single source of truth for supported image formats: this map gives both the suffixes we discover and the MIME type
# used in the data URL sent to the model, so the two can never drift. These are the formats OpenAI-compatible vision
# endpoints document support for (PNG, JPEG, WEBP, non-animated GIF). BMP/TIFF and friends are omitted because backends
# do not accept them reliably (notably the OpenAI cloud reference). Add a suffix here to support it everywhere at once.
IMAGE_MIME_BY_SUFFIX: dict[str, str] = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
}
IMAGE_SUFFIXES: frozenset[str] = frozenset(IMAGE_MIME_BY_SUFFIX)


class Verdict(StrEnum):
  """Outcome of evaluating a single rule against a single chart image."""

  PASS = "pass"  # noqa: S105 - verdict value, not a credential
  FAIL = "fail"
  NOT_APPLICABLE = "not_applicable"


class Rule(BaseModel):
  """A single check applied to a chart image.

  ``prompt`` is the load-bearing text handed to the model; ``summary`` is a short human label. ``prompt`` may contain
  ``{palette}`` / ``{fonts}`` placeholders that are filled from config when the request is built.

  ``na_without`` names the ``Config`` field (e.g. ``palette``) whose emptiness makes this rule deterministically
  ``not_applicable``: with nothing configured there is nothing to judge against, so the checker resolves the verdict
  itself and never sends the rule to the model. ``None`` (the default) means the rule always applies.
  """

  id: RuleId
  summary: str
  prompt: str
  enabled_by_default: bool = True
  na_without: str | None = None


class RuleVerdict(BaseModel):
  """The model's judgement for one rule on one image."""

  rule_id: RuleId
  verdict: Verdict
  rationale: str


class ImageReport(BaseModel):
  """All rule verdicts for a single chart image."""

  image: str
  verdicts: list[RuleVerdict]

  @computed_field
  @property
  def ok(self) -> bool:
    """Report whether this image passed every rule.

    :return: True when no rule failed; ``not_applicable`` never counts as a failure.
    """
    return all(v.verdict is not Verdict.FAIL for v in self.verdicts)


class Report(BaseModel):
  """The full result of a check run across one or more images."""

  images: list[ImageReport]

  @computed_field
  @property
  def ok(self) -> bool:
    """Report whether the whole run is clean.

    :return: True when every image passed; this drives the process exit code.
    """
    return all(image.ok for image in self.images)

  def to_json(self) -> str:
    """Render the report as deterministic, sorted-key JSON for stdout.

    :return: A JSON string with sorted keys and two-space indentation.
    """
    return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True)
