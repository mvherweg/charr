"""Tests for the runner that joins a manifest's labels to saved predictions and folds them into substrate records."""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from charr.models import RuleId, Verdict
from charr_eval.manifest import ManifestRecord, resolve_image
from charr_eval.predictions import PredictionsByImage
from charr_eval.runner import evaluate_manifest


def _record(image: str, labels: Mapping[RuleId, Verdict]) -> ManifestRecord:
  return ManifestRecord(image=image, library="matplotlib", labels=dict(labels))


def _predictions(manifest: Path, table: Mapping[str, Mapping[RuleId, tuple[Verdict, str]]]) -> PredictionsByImage:
  """Build a predictions lookup keyed by the same resolved paths the runner derives from the manifest."""
  return {resolve_image(manifest, _record(image, {})): dict(per_rule) for image, per_rule in table.items()}


def test_runner_records_one_substrate_entry_per_image_and_rule(
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
) -> None:
  records = [_record("images/a.png", {"has-title": Verdict.FAIL, "axes-labeled": Verdict.PASS})]
  manifest = make_dataset(records)
  predictions = _predictions(
    manifest,
    {"images/a.png": {"has-title": (Verdict.FAIL, "no title"), "axes-labeled": (Verdict.PASS, "labelled")}},
  )
  substrate, consumed = evaluate_manifest(manifest, name="config-00", predictions=predictions)
  assert len(substrate) == 2
  assert consumed == {resolve_image(manifest, records[0])}
  by_rule = {entry.rule_id: entry for entry in substrate}
  assert by_rule["has-title"].truth is Verdict.FAIL
  assert by_rule["has-title"].predicted is Verdict.FAIL
  assert by_rule["has-title"].manifest == "config-00"  # the runner stamps the caller-supplied name verbatim
  assert by_rule["has-title"].raw == "no title"  # the model's rationale is captured for failure analysis
  assert by_rule["has-title"].error is None


def test_runner_captures_disagreement(make_dataset: Callable[[Sequence[ManifestRecord]], Path]) -> None:
  manifest = make_dataset([_record("images/a.png", {"has-title": Verdict.FAIL})])
  predictions = _predictions(manifest, {"images/a.png": {"has-title": (Verdict.PASS, "looks fine")}})
  [entry], _ = evaluate_manifest(manifest, name="config-00", predictions=predictions)
  assert entry.truth is Verdict.FAIL
  assert entry.predicted is Verdict.PASS


def test_runner_folds_a_missing_prediction_into_the_error_bucket(
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
) -> None:
  manifest = make_dataset([_record("images/a.png", {"has-title": Verdict.FAIL})])
  [entry], consumed = evaluate_manifest(manifest, name="config-00", predictions={})
  assert entry.predicted is None
  assert "no prediction for image" in (entry.error or "")
  assert consumed == set()


def test_runner_folds_a_rule_absent_from_the_predictions_into_the_error_bucket(
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
) -> None:
  # The image is predicted, but a rule the manifest labels is missing from that image's verdicts (e.g. disabled at
  # check time): that one cell degrades to the error bucket rather than being dropped.
  manifest = make_dataset([_record("images/a.png", {"has-title": Verdict.FAIL, "axes-labeled": Verdict.PASS})])
  predictions = _predictions(manifest, {"images/a.png": {"has-title": (Verdict.FAIL, "no title")}})
  substrate, _ = evaluate_manifest(manifest, name="config-00", predictions=predictions)
  by_rule = {entry.rule_id: entry for entry in substrate}
  assert by_rule["has-title"].predicted is Verdict.FAIL
  assert by_rule["axes-labeled"].predicted is None
  assert "not evaluated" in (by_rule["axes-labeled"].error or "")
