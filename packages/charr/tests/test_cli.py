"""End-to-end tests for the CLI: exit codes and JSON output, with the LLM client stubbed."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from charr import cli
from charr.config import Config
from charr.llm import CheckResponse
from charr.models import Rule, RuleId, RuleVerdict, Verdict


class _StubClient:
  """Stands in for OpenAiCompatClient: returns a verdict per requested rule (default pass)."""

  def __init__(self, overrides: Mapping[RuleId, Verdict]) -> None:
    self._overrides = dict(overrides)

  def check_image(self, *, image: Path, rules: Sequence[Rule], config: Config) -> CheckResponse:  # noqa: ARG002
    return CheckResponse(
      results=[
        RuleVerdict(rule_id=rule.id, verdict=self._overrides.get(rule.id, Verdict.PASS), rationale="r")
        for rule in rules
      ],
    )


def _install_stub(monkeypatch: pytest.MonkeyPatch, overrides: Mapping[RuleId, Verdict]) -> None:
  def factory(*_args: object, **_kwargs: object) -> _StubClient:
    return _StubClient(overrides)

  monkeypatch.setattr(cli, "OpenAiCompatClient", factory)


def _set_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setenv("CHARR_LLM_BASE_URL", "http://localhost:11434/v1")
  monkeypatch.setenv("CHARR_LLM_MODEL", "vlm")


def test_main_returns_zero_and_prints_json_when_all_rules_pass(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  png_file: Path,
) -> None:
  _set_credentials(monkeypatch)
  monkeypatch.chdir(png_file.parent)
  _install_stub(monkeypatch, {})
  code = cli.main(["check", png_file.name])
  assert code == cli.EXIT_OK
  parsed = json.loads(capsys.readouterr().out)
  assert parsed["ok"] is True


def test_main_returns_one_when_a_rule_fails(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  png_file: Path,
) -> None:
  _set_credentials(monkeypatch)
  monkeypatch.chdir(png_file.parent)
  _install_stub(monkeypatch, {"has-title": Verdict.FAIL})
  code = cli.main(["check", png_file.name])
  assert code == cli.EXIT_RULE_FAILED
  parsed = json.loads(capsys.readouterr().out)
  assert parsed["ok"] is False


def test_main_returns_two_when_credentials_are_missing(
  monkeypatch: pytest.MonkeyPatch,
  png_file: Path,
) -> None:
  for name in ("CHARR_LLM_BASE_URL", "CHARR_LLM_MODEL", "CHARR_LLM_API_KEY"):
    monkeypatch.delenv(name, raising=False)
  monkeypatch.chdir(png_file.parent)
  assert cli.main(["check", png_file.name]) == cli.EXIT_CANNOT_RUN


def test_main_returns_two_when_no_inputs_match(
  monkeypatch: pytest.MonkeyPatch,
  tmp_path: Path,
) -> None:
  _set_credentials(monkeypatch)
  monkeypatch.chdir(tmp_path)
  assert cli.main(["check", "missing.png"]) == cli.EXIT_CANNOT_RUN


def test_cli_requires_a_subcommand() -> None:
  with pytest.raises(SystemExit):
    cli.build_parser().parse_args([])


def test_check_requires_at_least_one_input() -> None:
  with pytest.raises(SystemExit):
    cli.build_parser().parse_args(["check"])
