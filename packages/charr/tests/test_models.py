"""Tests for the domain models and the report's JSON rendering."""

import json

from charr.models import ImageReport, Report, RuleVerdict, Verdict


def _verdict(rule_id: str, verdict: Verdict) -> RuleVerdict:
  return RuleVerdict(rule_id=rule_id, verdict=verdict, rationale="because")


def test_image_report_ok_is_false_only_when_a_rule_fails_not_for_not_applicable() -> None:
  passing = ImageReport(image="a.png", verdicts=[_verdict("has-title", Verdict.PASS)])
  not_applicable = ImageReport(image="b.png", verdicts=[_verdict("axis-units", Verdict.NOT_APPLICABLE)])
  failing = ImageReport(image="c.png", verdicts=[_verdict("has-title", Verdict.FAIL)])
  assert passing.ok is True
  assert not_applicable.ok is True
  assert failing.ok is False


def test_report_ok_is_false_when_any_image_has_a_failing_rule() -> None:
  good = ImageReport(image="a.png", verdicts=[_verdict("has-title", Verdict.PASS)])
  bad = ImageReport(image="b.png", verdicts=[_verdict("has-title", Verdict.FAIL)])
  assert Report(images=[good]).ok is True
  assert Report(images=[good, bad]).ok is False


def test_report_to_json_is_stable_and_sorted_for_deterministic_output() -> None:
  report = Report(images=[ImageReport(image="a.png", verdicts=[_verdict("has-title", Verdict.PASS)])])
  rendered = report.to_json()
  # Sorted keys make the output deterministic across runs and machines.
  assert rendered == json.dumps(json.loads(rendered), indent=2, sort_keys=True)
  parsed = json.loads(rendered)
  assert parsed["ok"] is True
  assert parsed["images"][0]["verdicts"][0]["verdict"] == "pass"
  assert parsed["images"][0]["ok"] is True
