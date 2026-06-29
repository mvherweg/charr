"""Tests for the generation orchestration: per-config artifacts, the sweep, determinism, and the plotly font-NA rule.

These render with matplotlib only (pinned) so they stay deterministic and avoid the optional plotly path; image bytes
are never asserted, only structure and labels (the variable-by-platform pixels are out of scope per docs/adr/0014). The
one plotly-specific test fakes the backend so it runs offline.
"""

import json
from pathlib import Path

import pytest
from charr.models import Verdict
from charr_datagen import generate as gen
from charr_datagen.cells import build_cells
from charr_datagen.dataset import read_manifest
from charr_datagen.generate import DatagenError, generate, resolve_libraries
from charr_datagen.rendering import Backend
from charr_datagen.rendering import get_backend as real_get_backend


def test_generate_writes_per_config_artifacts(tmp_path: Path) -> None:
  result = generate(tmp_path / "set", libraries=["matplotlib"])
  config_dir = tmp_path / "set" / "config-00"
  records = read_manifest(config_dir / gen.MANIFEST_NAME)
  assert len(records) == len(build_cells())
  assert result.image_count == len(records)
  for record in records:
    assert (config_dir / record.image).is_file()
  config_text = (config_dir / gen.CONFIG_NAME).read_text(encoding="ascii")
  assert "palette = " in config_text
  assert "fonts = " in config_text
  config_meta = json.loads((config_dir / gen.META_NAME).read_text(encoding="ascii"))
  assert config_meta["config"] == "config-00"
  assert config_meta["palette"]
  assert config_meta["fonts"]
  # A copied config-NN must stay reproducible in isolation (docs/adr/0019), so it carries the run inputs too.
  assert config_meta["seed"] == 0
  assert config_meta["samples_per_config"] == len(build_cells())
  assert config_meta["libraries"] == ["matplotlib"]
  assert config_meta["charr_datagen_version"]


def test_generate_writes_a_run_index(tmp_path: Path) -> None:
  generate(tmp_path / "set", configs=2, libraries=["matplotlib"])
  meta = json.loads((tmp_path / "set" / gen.META_NAME).read_text(encoding="ascii"))
  assert meta["seed"] == 0
  assert meta["config_count"] == 2
  assert meta["libraries"] == ["matplotlib"]
  assert [config["config"] for config in meta["configs"]] == ["config-00", "config-01"]


def test_generate_sweep_writes_one_full_dataset_per_config(tmp_path: Path) -> None:
  cells = build_cells()
  result = generate(tmp_path / "set", samples=len(cells), configs=3, libraries=["matplotlib"])
  assert len(result.configs) == 3
  assert result.image_count == 3 * len(cells)
  for index in range(3):
    config_dir = tmp_path / "set" / f"config-{index:02d}"
    assert len(read_manifest(config_dir / gen.MANIFEST_NAME)) == len(cells)
  palettes = {tuple(item.config.palette) for item in result.configs}
  assert len(palettes) > 1, "independently sampled configs should differ"


def test_generate_is_deterministic_for_a_fixed_seed_and_library(tmp_path: Path) -> None:
  first = generate(tmp_path / "a", seed=3, configs=2, libraries=["matplotlib"])
  second = generate(tmp_path / "b", seed=3, configs=2, libraries=["matplotlib"])
  for index in range(2):
    name = f"config-{index:02d}"
    assert read_manifest(first.out_dir / name / gen.MANIFEST_NAME) == read_manifest(
      second.out_dir / name / gen.MANIFEST_NAME
    )


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


def test_plotly_images_carry_font_na_and_font_cells_avoid_plotly(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  # Fake plotly so the test runs offline: a backend that writes a stub file. We assert, through the public path, both
  # that plotly never renders a font-compliance cell and that any plotly image carries font-compliance: not_applicable.
  def fake_get_backend(name: str) -> Backend:
    if name == "plotly":

      def render_stub(_scene: object, out: Path) -> None:
        out.write_bytes(b"\x89PNG")

      return Backend("plotly", render_stub)
    return real_get_backend(name)

  monkeypatch.setattr(gen, "plotly_usable", lambda: True)
  monkeypatch.setattr(gen, "get_backend", fake_get_backend)
  result = generate(tmp_path / "set", samples=len(build_cells()) * 3)
  records = read_manifest(result.out_dir / "config-00" / gen.MANIFEST_NAME)
  plotly_records = [record for record in records if record.library == "plotly"]
  assert plotly_records, "expected some plotly images for non-font cells"
  for record in plotly_records:
    assert record.labels["font-compliance"] is Verdict.NOT_APPLICABLE
    assert "font-compliance" not in record.image  # a font cell must never have been rendered by plotly


def test_resolve_libraries_rejects_an_unknown_library() -> None:
  with pytest.raises(DatagenError, match="unknown rendering libraries"):
    resolve_libraries(["matplotlib", "ggplot"])


def test_resolve_libraries_rejects_a_plotly_only_pin(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setattr(gen, "plotly_usable", lambda: True)
  with pytest.raises(DatagenError, match="non-plotly backend"):
    resolve_libraries(["plotly"])


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
