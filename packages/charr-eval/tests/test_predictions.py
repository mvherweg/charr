"""Tests for loading a saved charr check output as the predictions the scorer joins against."""

from pathlib import Path

import pytest
from charr.models import CharrError, ImageReport, Report, RuleVerdict, Verdict
from charr_eval.predictions import load_predictions, prediction_image_key


def _report(*images: ImageReport) -> str:
  return Report(images=list(images)).to_json()


def test_load_predictions_indexes_verdicts_by_resolved_image_path(tmp_path: Path) -> None:
  image = tmp_path / "images" / "a.png"
  path = tmp_path / "check.json"
  path.write_text(
    _report(
      ImageReport(
        image=str(image), verdicts=[RuleVerdict(rule_id="has-title", verdict=Verdict.FAIL, rationale="no title")]
      )
    ),
    encoding="utf-8",
  )
  predictions = load_predictions(path)
  assert set(predictions) == {image.resolve()}
  assert predictions[image.resolve()]["has-title"] == (Verdict.FAIL, "no title")


def test_load_predictions_rejects_a_malformed_report(tmp_path: Path) -> None:
  path = tmp_path / "check.json"
  path.write_text("not json", encoding="utf-8")
  with pytest.raises(CharrError, match="invalid charr check output"):
    load_predictions(path)


def test_load_predictions_rejects_a_non_utf8_file(tmp_path: Path) -> None:
  # The wrong path handed in (e.g. a PNG or an archive) is bad input, not a crash. 0xFF is invalid UTF-8.
  path = tmp_path / "check.json"
  path.write_bytes(b"\xff\xfe not text")
  with pytest.raises(CharrError, match="invalid charr check output"):
    load_predictions(path)


def test_load_predictions_rejects_duplicate_image_entries(tmp_path: Path) -> None:
  image = tmp_path / "a.png"
  path = tmp_path / "check.json"
  path.write_text(
    _report(
      ImageReport(image=str(image), verdicts=[RuleVerdict(rule_id="has-title", verdict=Verdict.PASS, rationale="ok")]),
      ImageReport(image=str(image), verdicts=[RuleVerdict(rule_id="has-title", verdict=Verdict.FAIL, rationale="no")]),
    ),
    encoding="utf-8",
  )
  with pytest.raises(CharrError, match="duplicate prediction for image"):
    load_predictions(path)


def test_prediction_image_key_resolves_a_relative_path_against_the_current_directory(
  tmp_path: Path,
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  monkeypatch.chdir(tmp_path)
  assert prediction_image_key("images/a.png") == (tmp_path / "images" / "a.png").resolve()
