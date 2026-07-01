"""Tests for reading the manifest format and resolving image paths."""

from pathlib import Path

import pytest
from charr.models import CharrError, Verdict
from charr_eval.manifest import (
  ManifestRecord,
  discover_manifests,
  manifest_display_name,
  read_manifest,
  resolve_image,
)


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


def _write_manifest(path: Path) -> Path:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(_record().model_dump_json() + "\n", encoding="ascii")
  return path


def test_discover_manifests_walks_a_directory_recursively_in_sorted_order(tmp_path: Path) -> None:
  _write_manifest(tmp_path / "config-01" / "labels.jsonl")
  _write_manifest(tmp_path / "config-00" / "labels.jsonl")
  assert discover_manifests([tmp_path]) == [
    tmp_path / "config-00" / "labels.jsonl",
    tmp_path / "config-01" / "labels.jsonl",
  ]


def test_discover_manifests_ignores_a_directory_named_like_a_manifest(tmp_path: Path) -> None:
  (tmp_path / "decoy" / "labels.jsonl").mkdir(parents=True)  # a directory, not a manifest file
  real = _write_manifest(tmp_path / "real" / "labels.jsonl")
  assert discover_manifests([tmp_path]) == [real]


def test_discover_manifests_takes_an_explicit_file_even_if_not_named_labels(tmp_path: Path) -> None:
  manifest = _write_manifest(tmp_path / "curated.jsonl")
  assert discover_manifests([manifest]) == [manifest]


def test_discover_manifests_dedupes_an_overlapping_directory_and_file(tmp_path: Path) -> None:
  manifest = _write_manifest(tmp_path / "labels.jsonl")
  assert discover_manifests([tmp_path, manifest]) == [manifest]


def test_discover_manifests_rejects_a_missing_path(tmp_path: Path) -> None:
  with pytest.raises(CharrError, match="manifest path not found"):
    discover_manifests([tmp_path / "nope.jsonl"])


def test_discover_manifests_rejects_a_directory_without_manifests(tmp_path: Path) -> None:
  with pytest.raises(CharrError, match=r"no labels\.jsonl manifests under"):
    discover_manifests([tmp_path])


def test_manifest_display_name_is_the_resolved_absolute_path(tmp_path: Path) -> None:
  manifest = _write_manifest(tmp_path / "config-00" / "labels.jsonl")
  name = manifest_display_name(manifest)
  assert name == str(manifest.resolve())
  assert Path(name).is_absolute()
