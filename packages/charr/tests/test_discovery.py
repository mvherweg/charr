"""Tests for turning CLI inputs (files, globs, directories) into image paths."""

from collections.abc import Callable
from pathlib import Path

import pytest
from charr.discovery import DiscoveryError, discover_images


def test_discover_images_expands_directories_globs_and_files_into_sorted_unique_paths(
  tmp_path: Path,
  make_image: Callable[[Path], Path],
) -> None:
  charts = tmp_path / "charts"
  charts.mkdir()
  make_image(charts / "b.png")
  make_image(charts / "a.png")
  (charts / "notes.txt").write_text("ignore me")
  loose = make_image(tmp_path / "loose.jpg")
  found = discover_images(["charts", "loose.jpg"], cwd=tmp_path)
  assert found == [charts / "a.png", charts / "b.png", loose.resolve()]


def test_discover_images_expands_a_glob_to_matching_images_only(
  tmp_path: Path,
  make_image: Callable[[Path], Path],
) -> None:
  make_image(tmp_path / "one.png")
  make_image(tmp_path / "two.png")
  (tmp_path / "skip.txt").write_text("x")
  found = discover_images(["*.png"], cwd=tmp_path)
  assert found == [tmp_path / "one.png", tmp_path / "two.png"]


def test_discover_images_deduplicates_paths_listed_more_than_once(
  tmp_path: Path,
  make_image: Callable[[Path], Path],
) -> None:
  make_image(tmp_path / "chart.png")
  found = discover_images(["chart.png", "chart.png", "*.png"], cwd=tmp_path)
  assert found == [tmp_path / "chart.png"]


def test_discover_images_accepts_every_supported_suffix(
  tmp_path: Path,
  make_image: Callable[[Path], Path],
) -> None:
  names = {"a.png", "b.jpg", "c.jpeg", "d.webp", "e.gif"}
  for name in names:
    make_image(tmp_path / name)
  found = discover_images(["."], cwd=tmp_path)
  assert {path.name for path in found} == names


def test_discover_images_raises_when_an_input_matches_no_files(tmp_path: Path) -> None:
  with pytest.raises(DiscoveryError):
    discover_images(["missing.png"], cwd=tmp_path)


def test_discover_images_raises_when_a_directory_holds_no_images(tmp_path: Path) -> None:
  empty = tmp_path / "empty"
  empty.mkdir()
  with pytest.raises(DiscoveryError):
    discover_images(["empty"], cwd=tmp_path)


def test_discover_images_rejects_a_non_image_file_named_directly(tmp_path: Path) -> None:
  (tmp_path / "report.pdf").write_bytes(b"%PDF")
  with pytest.raises(DiscoveryError):
    discover_images(["report.pdf"], cwd=tmp_path)
