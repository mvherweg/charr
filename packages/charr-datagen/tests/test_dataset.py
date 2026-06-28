"""Tests for the JSONL manifest read/write round-trip."""

from pathlib import Path

import pytest
from charr.models import Verdict
from charr_datagen.dataset import ManifestRecord, read_manifest, write_manifest


def _record(image: str) -> ManifestRecord:
  return ManifestRecord(
    image=image,
    library="matplotlib",
    labels={"has-title": Verdict.FAIL, "axes-labeled": Verdict.PASS},
  )


def test_write_then_read_round_trips(tmp_path: Path) -> None:
  path = tmp_path / "labels.jsonl"
  records = [_record("images/a.png"), _record("images/b.png")]
  write_manifest(path, records)
  assert read_manifest(path) == records


def test_read_skips_blank_lines(tmp_path: Path) -> None:
  path = tmp_path / "labels.jsonl"
  body = _record("images/a.png").model_dump_json()
  path.write_text(f"\n{body}\n\n", encoding="ascii")
  assert read_manifest(path) == [_record("images/a.png")]


def test_read_rejects_a_malformed_line(tmp_path: Path) -> None:
  path = tmp_path / "labels.jsonl"
  path.write_text('{"image": "a.png"}\n', encoding="ascii")  # missing required fields
  with pytest.raises(ValueError, match="invalid manifest record"):
    read_manifest(path)
