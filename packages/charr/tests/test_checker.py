"""Tests for the orchestrator: per-image checking, verdict reconciliation, and aggregation."""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest
from charr.checker import CheckerError, run_check
from charr.config import Config, RuleSelection
from charr.llm import CheckResponse
from charr.models import Rule, RuleId, RuleVerdict, Verdict
from charr.rules import BUILTIN_RULES


class _StubClient:
  """LlmClient stub: returns one verdict per requested rule, defaulting to pass unless an override is given."""

  def __init__(self, overrides: Mapping[RuleId, Verdict] | None = None) -> None:
    self._overrides = dict(overrides or {})

  def check_image(self, *, image: Path, rules: Sequence[Rule], config: Config) -> CheckResponse:  # noqa: ARG002
    return CheckResponse(
      results=[
        RuleVerdict(rule_id=rule.id, verdict=self._overrides.get(rule.id, Verdict.PASS), rationale="r")
        for rule in rules
      ],
    )


class _ScriptedClient:
  """LlmClient returning a fixed list of verdicts regardless of the requested rules (for reconciliation tests)."""

  def __init__(self, verdicts: list[RuleVerdict]) -> None:
    self._verdicts = verdicts

  def check_image(self, *, image: Path, rules: Sequence[Rule], config: Config) -> CheckResponse:  # noqa: ARG002
    return CheckResponse(results=list(self._verdicts))


def _verdicts(*pairs: tuple[RuleId, Verdict]) -> list[RuleVerdict]:
  return [RuleVerdict(rule_id=rule_id, verdict=verdict, rationale="r") for rule_id, verdict in pairs]


def test_run_check_reports_ok_when_every_rule_passes(png_file: Path) -> None:
  report = run_check([png_file], Config(), _StubClient())
  assert report.ok is True
  assert report.images[0].image == str(png_file)


def test_run_check_reports_failure_when_any_rule_verdict_is_fail(png_file: Path) -> None:
  report = run_check([png_file], Config(), _StubClient({"has-title": Verdict.FAIL}))
  assert report.ok is False
  assert report.images[0].ok is False


def test_run_check_treats_not_applicable_verdicts_as_non_failing(png_file: Path) -> None:
  report = run_check([png_file], Config(), _StubClient({"axis-units": Verdict.NOT_APPLICABLE}))
  assert report.ok is True


def test_run_check_produces_one_report_entry_per_image_in_order(
  tmp_path: Path,
  make_image: Callable[[Path], Path],
) -> None:
  images = [make_image(tmp_path / "a.png"), make_image(tmp_path / "b.png")]
  report = run_check(images, Config(), _StubClient())
  assert [entry.image for entry in report.images] == [str(image) for image in images]


def test_run_check_reorders_verdicts_into_requested_rule_order(png_file: Path) -> None:
  config = Config(rules=RuleSelection(enable=["has-title", "axes-labeled"]))
  scrambled = _verdicts(("axes-labeled", Verdict.PASS), ("has-title", Verdict.PASS))
  report = run_check([png_file], config, _ScriptedClient(scrambled))
  assert [verdict.rule_id for verdict in report.images[0].verdicts] == ["has-title", "axes-labeled"]


def test_run_check_raises_when_the_model_omits_a_requested_rule(png_file: Path) -> None:
  config = Config(rules=RuleSelection(enable=["has-title", "axes-labeled"]))
  client = _ScriptedClient(_verdicts(("has-title", Verdict.PASS)))
  with pytest.raises(CheckerError, match="omitted"):
    run_check([png_file], config, client)


def test_run_check_raises_when_the_model_returns_an_unknown_rule_id(png_file: Path) -> None:
  config = Config(rules=RuleSelection(enable=["has-title"]))
  client = _ScriptedClient(_verdicts(("has-title", Verdict.PASS), ("made-up", Verdict.PASS)))
  with pytest.raises(CheckerError, match="unknown"):
    run_check([png_file], config, client)


def test_run_check_raises_when_no_rules_are_enabled(png_file: Path) -> None:
  config = Config(rules=RuleSelection(disable=[rule.id for rule in BUILTIN_RULES]))
  with pytest.raises(CheckerError, match="no rules"):
    run_check([png_file], config, _StubClient())
