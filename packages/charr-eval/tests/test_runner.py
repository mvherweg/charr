"""Tests for the runner that drives the checker per image into substrate records."""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from charr.config import Config
from charr.llm import CheckResponse, LlmError
from charr.models import Rule, RuleId, RuleVerdict, Verdict
from charr_eval.manifest import ManifestRecord
from charr_eval.runner import evaluate_manifest


class _FakeClient:
  """Answers each rule from a per-image truth table; missing entries default to pass."""

  def __init__(self, truth_by_image: Mapping[str, Mapping[RuleId, Verdict]]) -> None:
    self._truth = truth_by_image

  def check_image(self, *, image: Path, rules: Sequence[Rule], config: Config) -> CheckResponse:  # noqa: ARG002
    labels = self._truth.get(image.name, {})
    return CheckResponse(
      results=[RuleVerdict(rule_id=r.id, verdict=labels.get(r.id, Verdict.PASS), rationale="stub") for r in rules],
    )


class _ExplodingClient:
  def check_image(self, *, image: Path, rules: Sequence[Rule], config: Config) -> CheckResponse:  # noqa: ARG002
    msg = "backend exploded"
    raise LlmError(msg)


def _record(image: str, labels: Mapping[RuleId, Verdict]) -> ManifestRecord:
  return ManifestRecord(image=image, library="matplotlib", labels=dict(labels))


def test_runner_records_one_substrate_entry_per_image_and_rule(
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
) -> None:
  records = [_record("images/a.png", {"has-title": Verdict.FAIL, "axes-labeled": Verdict.PASS})]
  manifest = make_dataset(records)
  client = _FakeClient({"a.png": {"has-title": Verdict.FAIL, "axes-labeled": Verdict.PASS}})
  substrate = evaluate_manifest(manifest, client=client, config=Config())
  assert len(substrate) == 2
  by_rule = {entry.rule_id: entry for entry in substrate}
  assert by_rule["has-title"].truth is Verdict.FAIL
  assert by_rule["has-title"].predicted is Verdict.FAIL
  assert by_rule["has-title"].manifest == "labels"
  assert by_rule["has-title"].error is None


def test_runner_captures_disagreement(make_dataset: Callable[[Sequence[ManifestRecord]], Path]) -> None:
  manifest = make_dataset([_record("images/a.png", {"has-title": Verdict.FAIL})])
  client = _FakeClient({"a.png": {"has-title": Verdict.PASS}})  # checker misses the violation
  [entry] = evaluate_manifest(manifest, client=client, config=Config())
  assert entry.truth is Verdict.FAIL
  assert entry.predicted is Verdict.PASS


def test_runner_folds_a_checker_error_into_the_error_bucket(
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
) -> None:
  manifest = make_dataset([_record("images/a.png", {"has-title": Verdict.FAIL})])
  [entry] = evaluate_manifest(manifest, client=_ExplodingClient(), config=Config())
  assert entry.predicted is None
  assert entry.error is not None


def test_runner_marks_a_missing_image_as_an_error(tmp_path: Path) -> None:
  manifest = tmp_path / "labels.jsonl"
  manifest.write_text(_record("images/missing.png", {"has-title": Verdict.PASS}).model_dump_json() + "\n", "ascii")
  [entry] = evaluate_manifest(manifest, client=_FakeClient({}), config=Config())
  assert entry.predicted is None
  assert "not found" in (entry.error or "")
