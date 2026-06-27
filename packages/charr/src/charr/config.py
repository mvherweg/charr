"""Configuration and credential loading: TOML discovery, env-var credentials, and CLI overrides.

Config comes from TOML (a standalone ``charr.toml`` or the ``[tool.charr]`` table of a ``pyproject.toml``), discovered
by walking up from the working directory. Credentials and the endpoint come from environment variables only, never from
the repo. ``start`` and ``env`` are parameters (not read implicitly) so this is testable without touching the real
process environment or cwd.
"""

import tomllib
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from charr.models import CharrError, RuleId

# Environment variables holding the LLM endpoint and credentials. Kept out of config files and the repo on purpose.
ENV_BASE_URL = "CHARR_LLM_BASE_URL"
ENV_API_KEY = "CHARR_LLM_API_KEY"
ENV_MODEL = "CHARR_LLM_MODEL"


class ConfigError(CharrError):
  """Raised when configuration or credentials are missing or malformed (the run cannot proceed)."""


class LlmSettings(BaseModel):
  """Endpoint and credentials for the OpenAI-compatible backend, sourced from environment variables."""

  base_url: str
  api_key: str | None
  model: str


class RuleSelection(BaseModel):
  """Which rules to run. Empty ``enable`` means 'use each rule's default'; ``disable`` always wins."""

  model_config = ConfigDict(extra="forbid")

  enable: list[RuleId] = Field(default_factory=list)
  disable: list[RuleId] = Field(default_factory=list)


class RuleException(BaseModel):
  """Provisional per-rule / per-chart opt-out. Parsed but NOT yet enforced; shape may change (see project.md)."""

  model_config = ConfigDict(extra="allow")

  rule: RuleId | None = None
  images: list[str] = Field(default_factory=list)
  reason: str | None = None


class Config(BaseModel):
  """Resolved checker configuration (rule selection plus palette/font expectations)."""

  model_config = ConfigDict(extra="forbid")

  rules: RuleSelection = Field(default_factory=RuleSelection)
  palette: list[str] = Field(default_factory=list)
  fonts: list[str] = Field(default_factory=list)
  exceptions: list[RuleException] = Field(default_factory=list)


def discover_config_file(start: Path) -> Path | None:
  """Walk up from ``start``, returning the first config file found.

  Within a directory a ``charr.toml`` wins over a ``pyproject.toml``; a ``pyproject.toml`` only counts when it actually
  carries a ``[tool.charr]`` table.

  :param start: Directory to start the upward search from.
  :return: The closest config file, or ``None`` when none is found up to the filesystem root.
  """
  for directory in (start, *start.parents):
    charr_toml = directory / "charr.toml"
    if charr_toml.is_file():
      return charr_toml
    pyproject = directory / "pyproject.toml"
    if pyproject.is_file() and _extract_charr_table(_read_toml(pyproject), require_tool_charr=True) is not None:
      return pyproject
  return None


def load_config(
  start: Path,
  *,
  enable: list[RuleId] | None = None,
  disable: list[RuleId] | None = None,
  config_path: Path | None = None,
) -> Config:
  """Discover and parse config, then layer CLI ``enable``/``disable`` on top of the file's selection.

  CLI selections augment the file's, so a CLI ``disable`` overrides a file ``enable`` (disable always wins downstream).

  :param start: Directory to discover the config from (ignored when ``config_path`` is given).
  :param enable: Extra rule ids to enable, applied over the file's selection.
  :param disable: Extra rule ids to disable, applied over the file's selection.
  :param config_path: Explicit config file to use instead of discovery.
  :return: The resolved configuration.
  :raises ConfigError: If the discovered or given config is malformed.
  """
  path = config_path if config_path is not None else discover_config_file(start)
  table = _charr_table(path) if path is not None else {}
  try:
    config = Config.model_validate(table)
  except (tomllib.TOMLDecodeError, ValueError) as exc:
    source = str(path) if path is not None else "<defaults>"
    msg = f"invalid Charr config in {source}: {exc}"
    raise ConfigError(msg) from exc
  merged = RuleSelection(
    enable=_dedup([*config.rules.enable, *(enable or [])]),
    disable=_dedup([*config.rules.disable, *(disable or [])]),
  )
  return config.model_copy(update={"rules": merged})


def load_llm_settings(env: Mapping[str, str]) -> LlmSettings:
  """Read the endpoint and credentials from environment variables.

  :param env: Environment mapping to read the ``CHARR_LLM_*`` variables from.
  :return: The resolved endpoint settings. ``CHARR_LLM_API_KEY`` is optional (local servers often need none).
  :raises ConfigError: If ``CHARR_LLM_BASE_URL`` or ``CHARR_LLM_MODEL`` is missing.
  """
  base_url = env.get(ENV_BASE_URL, "").strip()
  model = env.get(ENV_MODEL, "").strip()
  api_key = env.get(ENV_API_KEY, "").strip()
  missing = [name for name, value in ((ENV_BASE_URL, base_url), (ENV_MODEL, model)) if not value]
  if missing:
    msg = f"missing required environment variable(s): {', '.join(missing)}"
    raise ConfigError(msg)
  return LlmSettings(base_url=base_url.rstrip("/"), api_key=api_key or None, model=model)


def _charr_table(path: Path) -> dict[str, object]:
  """Read ``path`` and return its Charr config table (empty when the file has none)."""
  data = _read_toml(path)
  require = path.name == "pyproject.toml"
  return _extract_charr_table(data, require_tool_charr=require) or {}


def _extract_charr_table(data: Mapping[str, object], *, require_tool_charr: bool) -> dict[str, object] | None:
  """Pull the ``[tool.charr]`` table out of a parsed TOML document.

  ``pyproject.toml`` keeps our config under ``[tool.charr]`` (``require_tool_charr=True``). A standalone ``charr.toml``
  may either use ``[tool.charr]`` or put the keys at the top level, so when it is not required we fall back to the whole
  document.
  """
  tool = data.get("tool")
  if isinstance(tool, dict):
    charr = tool.get("charr")
    if isinstance(charr, dict):
      return {str(key): value for key, value in charr.items()}
  if require_tool_charr:
    return None
  return dict(data)


def _read_toml(path: Path) -> dict[str, object]:
  with path.open("rb") as handle:
    return tomllib.load(handle)


def _dedup(ids: list[RuleId]) -> list[RuleId]:
  return list(dict.fromkeys(ids))
