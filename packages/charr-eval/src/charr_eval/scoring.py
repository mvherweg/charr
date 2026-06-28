"""The confusion substrate and the metrics derived from it (docs/adr/0017).

Scoring is a pure function of a list of :class:`SubstrateRecord` -- one record per ``(manifest, image, rule)`` capturing
the ground-truth verdict, the checker's predicted verdict, and its raw output. The substrate is the persisted
failure-analysis artifact; every metric is a downstream view of it, so adding a metric never re-runs the checker.

The positive class is ``fail`` (the violation a checker exists to catch), so the headline per rule is precision and
recall on ``fail`` plus accuracy, and the overall figure is the macro-average across rules. A prediction that could not
be parsed into a verdict lands in an ``error`` bucket (modeled as ``predicted is None``) and is folded in as a
non-detection -- never dropped -- so a flaky endpoint shows up as missed violations rather than silent passes.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from charr.models import RuleId, Verdict
from charr.rules import BUILTIN_RULES
from pydantic import BaseModel

# A prediction is a Verdict, or None for the error bucket (output that could not be parsed into a verdict).
type Prediction = Verdict | None


class SubstrateRecord(BaseModel):
  """One ``(manifest, image, rule)`` cell of the confusion substrate, also the persisted analysis artifact."""

  manifest: str
  image: str
  rule_id: RuleId
  truth: Verdict
  predicted: Verdict | None
  raw: str | None = None
  error: str | None = None


@dataclass(frozen=True)
class RuleScore:
  """Per-rule metrics on the ``fail`` (violation) class, plus overall accuracy and supporting counts.

  ``precision`` and ``recall`` are ``None`` when undefined (no predicted or no actual violations, respectively); a
  ``None`` is excluded from the macro-average rather than counted as zero.
  """

  rule_id: RuleId
  support: int
  fail_support: int
  error_count: int
  precision: float | None
  recall: float | None
  accuracy: float


@dataclass(frozen=True)
class MacroAverage:
  """The mean of the per-rule metrics, each rule weighted equally (``None`` precision/recall excluded)."""

  precision: float | None
  recall: float | None
  accuracy: float | None


@dataclass(frozen=True)
class Section:
  """A scored slice of the substrate: a named group (overall, or one manifest) with its per-rule scores and macro."""

  name: str
  rule_scores: tuple[RuleScore, ...]
  macro: MacroAverage


@dataclass(frozen=True)
class Scoreboard:
  """The full result: an overall section plus one section per manifest (docs/adr/0011 reports per manifest)."""

  overall: Section
  per_manifest: tuple[Section, ...]


def build_scoreboard(records: list[SubstrateRecord]) -> Scoreboard:
  """Score the substrate overall and per manifest.

  :param records: All substrate records from a run.
  :return: The scoreboard; sections list rules in catalog order, restricted to rules present in ``records``.
  """
  overall = _section("overall", records)
  per_manifest = tuple(_section(name, group) for name, group in _group_by_manifest(records))
  return Scoreboard(overall=overall, per_manifest=per_manifest)


def score_rule(rule_id: RuleId, records: list[SubstrateRecord]) -> RuleScore:
  """Compute the per-rule metrics for ``rule_id`` from the records that concern it.

  :param rule_id: The rule to score.
  :param records: Substrate records already filtered to this rule.
  :return: The rule's score on the ``fail`` class plus accuracy and counts.
  """
  confusion: Counter[tuple[Verdict, Prediction]] = Counter((rec.truth, rec.predicted) for rec in records)
  support = sum(confusion.values())
  fail_support = sum(count for (truth, _), count in confusion.items() if truth is Verdict.FAIL)
  error_count = sum(count for (_, pred), count in confusion.items() if pred is None)

  true_positive = confusion[Verdict.FAIL, Verdict.FAIL]
  predicted_fail = sum(count for (_, pred), count in confusion.items() if pred is Verdict.FAIL)
  correct = sum(count for (truth, pred), count in confusion.items() if pred is truth)

  precision = _ratio(true_positive, predicted_fail)
  recall = _ratio(true_positive, fail_support)
  accuracy = correct / support if support else 0.0
  return RuleScore(
    rule_id=rule_id,
    support=support,
    fail_support=fail_support,
    error_count=error_count,
    precision=precision,
    recall=recall,
    accuracy=accuracy,
  )


def macro_average(scores: tuple[RuleScore, ...]) -> MacroAverage:
  """Average the per-rule metrics with equal weight per rule, skipping undefined precision/recall.

  :param scores: The per-rule scores to average.
  :return: The macro-average; a component is ``None`` when no rule defined it.
  """
  return MacroAverage(
    precision=_mean(score.precision for score in scores),
    recall=_mean(score.recall for score in scores),
    accuracy=_mean(score.accuracy for score in scores),
  )


def _section(name: str, records: list[SubstrateRecord]) -> Section:
  present = {rec.rule_id for rec in records}
  rule_ids = [rule.id for rule in BUILTIN_RULES if rule.id in present]
  rule_ids.extend(sorted(present - set(rule_ids)))  # any non-builtin rule ids, after the catalog ones
  scores = tuple(score_rule(rule_id, [rec for rec in records if rec.rule_id == rule_id]) for rule_id in rule_ids)
  return Section(name=name, rule_scores=scores, macro=macro_average(scores))


def _group_by_manifest(records: list[SubstrateRecord]) -> list[tuple[str, list[SubstrateRecord]]]:
  groups: dict[str, list[SubstrateRecord]] = {}
  for rec in records:
    groups.setdefault(rec.manifest, []).append(rec)
  return list(groups.items())


def _ratio(numerator: int, denominator: int) -> float | None:
  return numerator / denominator if denominator else None


def _mean(values: Iterable[float | None]) -> float | None:
  defined = [value for value in values if value is not None]
  return sum(defined) / len(defined) if defined else None
