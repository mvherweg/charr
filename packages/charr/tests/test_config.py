"""Tests for config discovery, parsing, CLI merge, and credential loading."""

from pathlib import Path

import pytest
from charr.config import ConfigError, discover_config_file, load_config, load_llm_settings


def test_config_discovery_walks_up_and_prefers_the_closest_charr_toml_over_pyproject(tmp_path: Path) -> None:
  (tmp_path / "pyproject.toml").write_text('[tool.charr]\npalette = ["#000000"]\n')
  nested = tmp_path / "team" / "project"
  nested.mkdir(parents=True)
  charr_toml = nested / "charr.toml"
  charr_toml.write_text('palette = ["#ffffff"]\n')
  assert discover_config_file(nested) == charr_toml


def test_config_discovery_returns_none_when_no_config_exists_up_the_tree(tmp_path: Path) -> None:
  empty = tmp_path / "deep" / "empty"
  empty.mkdir(parents=True)
  assert discover_config_file(empty) is None


def test_load_config_reads_palette_and_fonts_from_a_standalone_charr_toml(tmp_path: Path) -> None:
  (tmp_path / "charr.toml").write_text('palette = ["#112233"]\nfonts = ["Inter"]\n')
  config = load_config(tmp_path)
  assert config.palette == ["#112233"]
  assert config.fonts == ["Inter"]


def test_load_config_applies_cli_enable_and_disable_over_file_selection(tmp_path: Path) -> None:
  (tmp_path / "charr.toml").write_text('[rules]\nenable = ["has-title"]\n')
  config = load_config(tmp_path, enable=["axes-labeled"], disable=["has-title"])
  assert config.rules.enable == ["has-title", "axes-labeled"]
  assert config.rules.disable == ["has-title"]


def test_load_config_rejects_unknown_config_keys(tmp_path: Path) -> None:
  (tmp_path / "charr.toml").write_text("bogus_key = 1\n")
  with pytest.raises(ConfigError):
    load_config(tmp_path)


def test_load_config_raises_config_error_for_a_missing_explicit_config_path(tmp_path: Path) -> None:
  with pytest.raises(ConfigError):
    load_config(tmp_path, config_path=tmp_path / "does-not-exist.toml")


def test_load_config_raises_config_error_for_malformed_toml(tmp_path: Path) -> None:
  (tmp_path / "charr.toml").write_text("[unterminated section\n")
  with pytest.raises(ConfigError):
    load_config(tmp_path)


def test_load_llm_settings_reads_endpoint_and_strips_a_trailing_slash() -> None:
  settings = load_llm_settings(
    {"CHARR_LLM_BASE_URL": "http://localhost:11434/v1/", "CHARR_LLM_MODEL": "qwen2-vl"},
  )
  assert settings.base_url == "http://localhost:11434/v1"
  assert settings.model == "qwen2-vl"
  assert settings.api_key is None


def test_load_llm_settings_keeps_the_api_key_when_present() -> None:
  settings = load_llm_settings(
    {"CHARR_LLM_BASE_URL": "http://host/v1", "CHARR_LLM_MODEL": "m", "CHARR_LLM_API_KEY": "secret"},
  )
  assert settings.api_key == "secret"


def test_load_llm_settings_raises_a_clear_error_when_base_url_or_model_env_missing() -> None:
  with pytest.raises(ConfigError, match="CHARR_LLM_BASE_URL"):
    load_llm_settings({"CHARR_LLM_MODEL": "m"})
  with pytest.raises(ConfigError, match="CHARR_LLM_MODEL"):
    load_llm_settings({"CHARR_LLM_BASE_URL": "http://host/v1"})
