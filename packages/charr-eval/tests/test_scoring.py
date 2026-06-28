"""Tests for the confusion substrate and the fail-class metrics derived from it."""

from charr.models import RuleId, Verdict
from charr_eval.scoring import SubstrateRecord, build_scoreboard, macro_average, score_rule


def substrate(
  truth: Verdict, predicted: Verdict | None, *, rule_id: RuleId = "r", manifest: str = "m"
) -> SubstrateRecord:
  return SubstrateRecord(manifest=manifest, image="i.png", rule_id=rule_id, truth=truth, predicted=predicted)


def test_precision_and_recall_are_measured_on_the_fail_class() -> None:
  records = [
    substrate(Verdict.FAIL, Verdict.FAIL),  # true positive
    substrate(Verdict.PASS, Verdict.FAIL),  # false positive
    substrate(Verdict.FAIL, Verdict.PASS),  # false negative
    substrate(Verdict.PASS, Verdict.PASS),  # true negative
  ]
  score = score_rule("r", records)
  assert score.precision == 0.5  # 1 TP / (1 TP + 1 FP)
  assert score.recall == 0.5  # 1 TP / (1 TP + 1 FN)
  assert score.accuracy == 0.5  # 2 correct / 4
  assert score.support == 4
  assert score.fail_support == 2


def test_an_error_prediction_counts_as_a_missed_violation() -> None:
  records = [substrate(Verdict.FAIL, None), substrate(Verdict.FAIL, Verdict.FAIL)]
  score = score_rule("r", records)
  assert score.error_count == 1
  assert score.recall == 0.5  # one of two real violations caught; the errored one is a miss
  assert score.precision == 1.0  # the single predicted fail was correct


def test_precision_is_undefined_when_nothing_is_predicted_as_fail() -> None:
  score = score_rule("r", [substrate(Verdict.FAIL, Verdict.PASS), substrate(Verdict.PASS, Verdict.PASS)])
  assert score.precision is None
  assert score.recall == 0.0


def test_recall_is_undefined_when_there_are_no_actual_violations() -> None:
  score = score_rule("r", [substrate(Verdict.PASS, Verdict.PASS), substrate(Verdict.NOT_APPLICABLE, Verdict.PASS)])
  assert score.recall is None


def test_macro_average_skips_undefined_components() -> None:
  defined = score_rule("a", [substrate(Verdict.FAIL, Verdict.FAIL)])
  undefined = score_rule("b", [substrate(Verdict.PASS, Verdict.PASS)])  # recall undefined here
  macro = macro_average((defined, undefined))
  assert macro.recall == 1.0  # only rule a contributes a defined recall
  assert macro.accuracy == 1.0


def test_build_scoreboard_reports_overall_and_per_manifest() -> None:
  records = [
    substrate(Verdict.FAIL, Verdict.FAIL, manifest="alpha"),
    substrate(Verdict.FAIL, Verdict.PASS, manifest="beta"),
  ]
  board = build_scoreboard(records)
  assert board.overall.rule_scores[0].support == 2
  assert {section.name for section in board.per_manifest} == {"alpha", "beta"}
