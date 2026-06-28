"""Tests for the generation orchestration: artifacts, determinism, library policy, and coverage handling.

These render with matplotlib only (pinned) so they stay deterministic and avoid the optional plotly path; image bytes
are never asserted, only structure and labels (the variable-by-platform pixels are out of scope per docs/adr/0014).
"""

import json
from pathlib import Path

import pytest
from charr_datagen import generate as gen
from charr_datagen.cells import build_cells
from charr_datagen.dataset import read_manifest
from charr_datagen.generate import DatagenError, generate, resolve_libraries


def test_generate_writes_all_artifacts(tmp_path: Path) -> None:
  result = generate(tmp_path / "set", libraries=["matplotlib"])
  out = tmp_path / "set"
  records = read_manifest(out / gen.MANIFEST_NAME)
  assert len(records) == len(build_cells())
  assert result.image_count == len(records)
  for record in records:
    assert (out / record.image).is_file()
  config_text = (out / gen.CONFIG_NAME).read_text(encoding="ascii")
  assert "palette = " in config_text
  assert "fonts = " in config_text
  meta = json.loads((out / gen.META_NAME).read_text(encoding="ascii"))
  assert meta["libraries"] == ["matplotlib"]
  assert meta["seed"] == 0
  assert len(meta["cells"]) == len(build_cells())


def test_generate_is_deterministic_for_a_fixed_seed_and_library(tmp_path: Path) -> None:
  first = generate(tmp_path / "a", seed=3, libraries=["matplotlib"])
  second = generate(tmp_path / "b", seed=3, libraries=["matplotlib"])
  assert read_manifest(first.out_dir / gen.MANIFEST_NAME) == read_manifest(second.out_dir / gen.MANIFEST_NAME)


def test_generate_errors_when_the_output_parent_is_missing(tmp_path: Path) -> None:
  with pytest.raises(DatagenError, match="parent directory does not exist"):
    generate(tmp_path / "missing" / "set", libraries=["matplotlib"])


def test_generate_strict_coverage_errors_when_under_budget(tmp_path: Path) -> None:
  with pytest.raises(DatagenError, match="under-budget"):
    generate(tmp_path / "set", samples=3, libraries=["matplotlib"], strict_coverage=True)


def test_generate_warns_and_proceeds_when_under_budget(tmp_path: Path) -> None:
  result = generate(tmp_path / "set", samples=3, libraries=["matplotlib"])
  assert result.image_count == 3
  assert result.uncovered
  assert any("under-budget" in message for message in result.messages)


def test_resolve_libraries_rejects_an_unknown_library() -> None:
  with pytest.raises(DatagenError, match="unknown rendering libraries"):
    resolve_libraries(["matplotlib", "ggplot"])


def test_resolve_libraries_default_drops_plotly_with_a_message_when_unusable(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setattr(gen, "plotly_usable", lambda: False)
  active, messages = resolve_libraries(None)
  assert active == ["matplotlib", "seaborn"]
  assert any("plotly disabled" in message for message in messages)


def test_resolve_libraries_default_includes_plotly_when_usable(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setattr(gen, "plotly_usable", lambda: True)
  active, messages = resolve_libraries(None)
  assert active == ["matplotlib", "seaborn", "plotly"]
  assert messages == []


def test_resolve_libraries_errors_when_plotly_is_pinned_but_unusable(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setattr(gen, "plotly_usable", lambda: False)
  with pytest.raises(DatagenError, match="plotly was pinned"):
    resolve_libraries(["plotly"])
