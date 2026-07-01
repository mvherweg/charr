"""Tests for reading the manifest format and resolving image paths."""

from pathlib import Path

import pytest
from charr.models import CharrError, Verdict
from charr_eval.manifest import ManifestRecord, read_manifest, resolve_image


def _record(image: str = "images/a.png") -> ManifestRecord:
  return ManifestRecord(image=image, library="seaborn", labels={"has-title": Verdict.PASS})


def test_read_manifest_parses_records(tmp_path: Path) -> None:
  path = tmp_path / "labels.jsonl"
  path.write_text(_record().model_dump_json() + "\n", encoding="ascii")
  assert read_manifest(path) == [_record()]


def test_read_manifest_skips_blank_lines(tmp_path: Path) -> None:
  path = tmp_path / "labels.jsonl"
  path.write_text(f"\n{_record().model_dump_json()}\n\n", encoding="ascii")
  assert read_manifest(path) == [_record()]


def test_read_manifest_rejects_a_malformed_line(tmp_path: Path) -> None:
  path = tmp_path / "labels.jsonl"
  path.write_text("not json\n", encoding="ascii")
  with pytest.raises(CharrError, match="invalid manifest record"):
    read_manifest(path)


def test_resolve_image_is_relative_to_the_manifest_directory(tmp_path: Path) -> None:
  manifest = tmp_path / "sub" / "labels.jsonl"
  resolved = resolve_image(manifest, _record("images/a.png"))
  assert resolved == (tmp_path / "sub" / "images" / "a.png").resolve()
