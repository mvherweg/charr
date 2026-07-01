"""Tests for the evaluator CLI: the offline end-to-end path with a fake backend, and the report formatter."""

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from charr.config import Config
from charr.llm import CheckResponse
from charr.models import Rule, RuleVerdict, Verdict
from charr_eval import cli
from charr_eval.manifest import ManifestRecord
from charr_eval.scoring import MacroAverage, RuleScore, Scoreboard, Section


class _PassClient:
  """A stand-in backend that passes every rule; enough to exercise the CLI without a network."""

  def check_image(self, *, image: Path, rules: Sequence[Rule], config: Config) -> CheckResponse:  # noqa: ARG002
    return CheckResponse(results=[RuleVerdict(rule_id=r.id, verdict=Verdict.PASS, rationale="ok") for r in rules])


def _set_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setenv("CHARR_LLM_BASE_URL", "http://localhost:1234/v1")
  monkeypatch.setenv("CHARR_LLM_MODEL", "fake-model")


def test_main_scores_a_manifest_end_to_end_with_a_fake_backend(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
  tmp_path: Path,
) -> None:
  _set_credentials(monkeypatch)
  monkeypatch.setattr(cli, "OpenAiCompatClient", lambda *args, **kwargs: _PassClient())  # noqa: ARG005
  manifest = make_dataset(
    [ManifestRecord(image="images/a.png", library="matplotlib", labels={"has-title": Verdict.PASS})]
  )
  substrate_out = tmp_path / "substrate.jsonl"
  exit_code = cli.main([str(manifest), "--substrate-out", str(substrate_out)])
  assert exit_code == cli.EXIT_OK
  assert "== overall ==" in capsys.readouterr().out
  assert substrate_out.is_file()
  assert substrate_out.read_text(encoding="ascii").strip()


def test_main_returns_cannot_run_without_credentials(
  monkeypatch: pytest.MonkeyPatch,
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
) -> None:
  monkeypatch.delenv("CHARR_LLM_BASE_URL", raising=False)
  monkeypatch.delenv("CHARR_LLM_MODEL", raising=False)
  manifest = make_dataset(
    [ManifestRecord(image="images/a.png", library="matplotlib", labels={"has-title": Verdict.PASS})]
  )
  assert cli.main([str(manifest)]) == cli.EXIT_CANNOT_RUN


def test_main_returns_cannot_run_for_a_missing_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
  _set_credentials(monkeypatch)
  monkeypatch.setattr(cli, "OpenAiCompatClient", lambda *args, **kwargs: _PassClient())  # noqa: ARG005
  assert cli.main([str(tmp_path / "nope.jsonl")]) == cli.EXIT_CANNOT_RUN


def test_main_returns_cannot_run_for_a_malformed_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
  _set_credentials(monkeypatch)
  monkeypatch.setattr(cli, "OpenAiCompatClient", lambda *args, **kwargs: _PassClient())  # noqa: ARG005
  manifest = tmp_path / "labels.jsonl"
  manifest.write_text("not json\n", encoding="utf-8")
  assert cli.main([str(manifest)]) == cli.EXIT_CANNOT_RUN


def test_main_does_not_mask_an_unexpected_error_as_cannot_run(
  monkeypatch: pytest.MonkeyPatch,
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
) -> None:
  # A programming fault (here a stand-in ValueError from persistence, as a UnicodeEncodeError once was) must crash,
  # not be swallowed into exit 2 - otherwise real bugs masquerade as "cannot run".
  _set_credentials(monkeypatch)
  monkeypatch.setattr(cli, "OpenAiCompatClient", lambda *args, **kwargs: _PassClient())  # noqa: ARG005

  def _boom(*args: object, **kwargs: object) -> None:  # noqa: ARG001
    msg = "unexpected fault"
    raise ValueError(msg)

  monkeypatch.setattr(cli, "_persist_substrate", _boom)
  manifest = make_dataset(
    [ManifestRecord(image="images/a.png", library="matplotlib", labels={"has-title": Verdict.PASS})]
  )
  with pytest.raises(ValueError, match="unexpected fault"):
    cli.main([str(manifest)])


def test_format_report_renders_overall_and_macro() -> None:
  score = RuleScore("has-title", support=2, fail_support=1, error_count=0, precision=1.0, recall=1.0, accuracy=1.0)
  macro = MacroAverage(precision=1.0, recall=1.0, accuracy=1.0)
  board = Scoreboard(overall=Section("overall", (score,), macro), per_manifest=())
  report = cli.format_report(board)
  assert "== overall ==" in report
  assert "has-title" in report
  assert "macro" in report
