"""Tests for the orchestrator: per-image checking, verdict reconciliation, and aggregation."""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest
from charr.checker import CheckerError, run_check
from charr.config import Config, RuleSelection
from charr.llm import CheckResponse
from charr.models import Rule, RuleId, RuleVerdict, Verdict
from charr.rules import BUILTIN_RULES

_GATED_RULES = [(rule.id, rule.na_without) for rule in BUILTIN_RULES if rule.na_without is not None]


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


class _SpyClient:
  """LlmClient stub that records which rules each call requested, so tests can assert what was (and was not) sent."""

  def __init__(self, overrides: Mapping[RuleId, Verdict] | None = None) -> None:
    self._overrides = dict(overrides or {})
    self.requested: list[list[RuleId]] = []

  def check_image(self, *, image: Path, rules: Sequence[Rule], config: Config) -> CheckResponse:  # noqa: ARG002
    self.requested.append([rule.id for rule in rules])
    return CheckResponse(
      results=[
        RuleVerdict(rule_id=rule.id, verdict=self._overrides.get(rule.id, Verdict.PASS), rationale="r")
        for rule in rules
      ],
    )


class _ExplodingClient:
  """LlmClient that fails if called: proves the checker never reaches the model when there is nothing to ask."""

  def check_image(self, *, image: Path, rules: Sequence[Rule], config: Config) -> CheckResponse:  # noqa: ARG002
    msg = "the model must not be called when every enabled rule resolves deterministically"
    raise AssertionError(msg)


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


@pytest.mark.parametrize(("rule_id", "field"), _GATED_RULES)
def test_run_check_forces_a_config_gated_rule_to_not_applicable_when_its_field_is_empty(
  png_file: Path,
  rule_id: RuleId,
  field: str,
) -> None:
  config = Config(rules=RuleSelection(enable=[rule_id]))  # default Config leaves palette and fonts empty
  client = _SpyClient({rule_id: Verdict.FAIL})  # the model would fail it, but it must never be asked
  report = run_check([png_file], config, client)
  verdict = report.images[0].verdicts[0]
  assert verdict.rule_id == rule_id
  assert verdict.verdict is Verdict.NOT_APPLICABLE
  assert field in verdict.rationale
  assert client.requested == []  # the rule was dropped from the request, leaving nothing to send


def test_run_check_still_sends_a_config_gated_rule_when_its_field_is_configured(png_file: Path) -> None:
  config = Config(rules=RuleSelection(enable=["palette-compliance"]), palette=["#112233"])
  client = _SpyClient({"palette-compliance": Verdict.FAIL})
  report = run_check([png_file], config, client)
  assert client.requested == [["palette-compliance"]]
  assert report.images[0].verdicts[0].verdict is Verdict.FAIL


def test_run_check_drops_only_the_unconfigured_gated_rule_and_keeps_the_others(png_file: Path) -> None:
  config = Config(rules=RuleSelection(enable=["has-title", "palette-compliance", "font-compliance"]), fonts=["Inter"])
  client = _SpyClient()
  report = run_check([png_file], config, client)
  assert client.requested == [["has-title", "font-compliance"]]  # palette dropped (empty), font kept (configured)
  by_id = {verdict.rule_id: verdict.verdict for verdict in report.images[0].verdicts}
  assert by_id["palette-compliance"] is Verdict.NOT_APPLICABLE
  assert by_id["has-title"] is Verdict.PASS
  assert by_id["font-compliance"] is Verdict.PASS


def test_run_check_never_calls_the_model_when_every_enabled_rule_is_gated_and_unconfigured(png_file: Path) -> None:
  config = Config(rules=RuleSelection(enable=["palette-compliance", "font-compliance"]))
  report = run_check([png_file], config, _ExplodingClient())
  assert report.ok is True  # not_applicable never fails the run
  assert all(verdict.verdict is Verdict.NOT_APPLICABLE for verdict in report.images[0].verdicts)
