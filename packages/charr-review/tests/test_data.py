"""Tests for the substrate reader: outcome classification, row building, warnings, and image resolution."""

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from charr.models import CharrError, Verdict
from charr_review.data import Outcome, SubstrateRecord, classify, load_rows, resolve_image_path

PASS, FAIL, NA = Verdict.PASS, Verdict.FAIL, Verdict.NOT_APPLICABLE

MakeReview = Callable[[Sequence[SubstrateRecord]], tuple[Path, Path]]


def _record(
  rule_id: str,
  truth: Verdict,
  predicted: Verdict | None,
  *,
  image: str = "images/0001-has-title-fail-matplotlib.png",
  raw: str | None = "because",
) -> SubstrateRecord:
  return SubstrateRecord(manifest="labels", image=image, rule_id=rule_id, truth=truth, predicted=predicted, raw=raw)


def test_classify_covers_every_confusion_outcome() -> None:
  assert classify(FAIL, FAIL) is Outcome.TP
  assert classify(FAIL, PASS) is Outcome.FN
  assert classify(PASS, FAIL) is Outcome.FP
  assert classify(PASS, PASS) is Outcome.TN
  assert classify(NA, NA) is Outcome.TN
  assert classify(FAIL, None) is Outcome.ERROR


def test_pass_versus_not_applicable_is_a_mismatch_even_though_the_outcome_is_tn(make_review: MakeReview) -> None:
  substrate, dataset = make_review([_record("has-title", PASS, NA)])
  row = load_rows(substrate, dataset).rows[0]
  assert row.outcome is Outcome.TN
  assert row.correct is False


def test_load_rows_builds_one_row_per_record_with_resolved_fields(make_review: MakeReview) -> None:
  records = [
    _record("has-title", FAIL, FAIL, raw="no title found"),
    _record("axes-labeled", PASS, PASS, image="images/0002-axes-labeled-pass-seaborn.png"),
  ]
  substrate, dataset = make_review(records)
  data = load_rows(substrate, dataset)
  assert [row.rule_id for row in data.rows] == ["has-title", "axes-labeled"]
  assert data.rows[0].outcome is Outcome.TP
  assert data.rows[0].rationale == "no title found"
  assert data.rows[0].library == "matplotlib"
  assert data.rows[0].polarity == "fail"
  assert data.summary["total"] == 2
  assert data.summary["TP"] == 1
  assert data.warnings == []


def test_parse_filename_yields_none_for_a_hand_authored_name(make_review: MakeReview) -> None:
  substrate, dataset = make_review([_record("has-title", FAIL, FAIL, image="images/chart.png")])
  row = load_rows(substrate, dataset).rows[0]
  assert row.library is None
  assert row.polarity is None


def test_load_rows_raises_charr_error_on_a_malformed_line(make_review: MakeReview) -> None:
  substrate, dataset = make_review([_record("has-title", FAIL, FAIL)])
  substrate.write_text("{ not json\n", encoding="ascii")
  with pytest.raises(CharrError):
    load_rows(substrate, dataset)


def test_load_rows_raises_charr_error_on_an_empty_substrate(make_review: MakeReview) -> None:
  substrate, dataset = make_review([_record("has-title", FAIL, FAIL)])
  substrate.write_text("\n\n", encoding="ascii")
  with pytest.raises(CharrError):
    load_rows(substrate, dataset)


def test_load_rows_warns_when_a_referenced_image_is_missing(make_review: MakeReview) -> None:
  substrate, dataset = make_review([_record("has-title", FAIL, FAIL)])
  for image in (dataset / "images").iterdir():
    image.unlink()
  data = load_rows(substrate, dataset)
  assert any("not found" in warning for warning in data.warnings)


def test_load_rows_warns_when_the_substrate_spans_multiple_datasets(make_review: MakeReview) -> None:
  # Two identical (manifest, image, rule) keys: the signature of a multi-config sweep collapsed into one substrate.
  record = _record("has-title", FAIL, FAIL)
  substrate, dataset = make_review([record, record])
  data = load_rows(substrate, dataset)
  assert any("multiple datasets" in warning for warning in data.warnings)


def test_resolve_image_path_rejects_a_path_escaping_the_dataset_dir(make_review: MakeReview) -> None:
  _, dataset = make_review([_record("has-title", FAIL, FAIL)])
  assert resolve_image_path(dataset, "../escape.png") is None


def test_resolve_image_path_returns_the_file_for_a_valid_image(make_review: MakeReview) -> None:
  _, dataset = make_review([_record("has-title", FAIL, FAIL)])
  resolved = resolve_image_path(dataset, "images/0001-has-title-fail-matplotlib.png")
  assert resolved is not None
  assert resolved.is_file()
