"""Tests for the review CLI: it loads rows and hands them to a (stubbed) server, and reports run failures."""

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from charr.models import Verdict
from charr_review import cli
from charr_review.data import ReviewData, SubstrateRecord

MakeReview = Callable[[Sequence[SubstrateRecord]], tuple[Path, Path]]


def _record(image: str = "images/0001-has-title-fail-matplotlib.png") -> SubstrateRecord:
  return SubstrateRecord(
    manifest="labels", image=image, rule_id="has-title", truth=Verdict.FAIL, predicted=Verdict.FAIL
  )


def test_main_loads_rows_and_serves(make_review: MakeReview, monkeypatch: pytest.MonkeyPatch) -> None:
  substrate, dataset = make_review([_record()])
  calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
  monkeypatch.setattr(cli, "serve", lambda *args, **kwargs: calls.append((args, kwargs)))
  exit_code = cli.main([str(substrate), "-d", str(dataset), "--no-open"])
  assert exit_code == cli.EXIT_OK
  assert len(calls) == 1
  served = calls[0][0][0]
  assert isinstance(served, ReviewData)
  assert served.rows[0].rule_id == "has-title"
  assert calls[0][1]["open_browser"] is False


def test_main_returns_cannot_run_for_a_missing_substrate(
  make_review: MakeReview,
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  tmp_path: Path,
) -> None:
  _, dataset = make_review([_record()])
  monkeypatch.setattr(cli, "serve", lambda *args, **kwargs: None)  # noqa: ARG005
  assert cli.main([str(tmp_path / "nope.jsonl"), "-d", str(dataset)]) == cli.EXIT_CANNOT_RUN
  assert "substrate not found" in capsys.readouterr().err


def test_main_returns_cannot_run_for_a_missing_dataset_dir(
  make_review: MakeReview,
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  tmp_path: Path,
) -> None:
  substrate, _ = make_review([_record()])
  monkeypatch.setattr(cli, "serve", lambda *args, **kwargs: None)  # noqa: ARG005
  assert cli.main([str(substrate), "-d", str(tmp_path / "nodir")]) == cli.EXIT_CANNOT_RUN
  assert "dataset dir not found" in capsys.readouterr().err


def test_main_returns_cannot_run_for_a_malformed_substrate(
  make_review: MakeReview,
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
) -> None:
  substrate, dataset = make_review([_record()])
  substrate.write_text("{ not json\n", encoding="ascii")
  monkeypatch.setattr(cli, "serve", lambda *args, **kwargs: None)  # noqa: ARG005
  assert cli.main([str(substrate), "-d", str(dataset), "--no-open"]) == cli.EXIT_CANNOT_RUN
  assert "malformed substrate" in capsys.readouterr().err


def test_main_prints_warnings_to_stderr(
  make_review: MakeReview,
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
) -> None:
  record = _record()
  substrate, dataset = make_review([record, record])
  monkeypatch.setattr(cli, "serve", lambda *args, **kwargs: None)  # noqa: ARG005
  assert cli.main([str(substrate), "-d", str(dataset), "--no-open"]) == cli.EXIT_OK
  assert "warning" in capsys.readouterr().err
