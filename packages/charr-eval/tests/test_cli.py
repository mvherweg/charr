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
  assert substrate_out.read_text(encoding="utf-8").strip()


def test_main_discovers_manifests_under_a_directory_and_names_them_by_absolute_path(
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  tmp_path: Path,
) -> None:
  _set_credentials(monkeypatch)
  monkeypatch.setattr(cli, "OpenAiCompatClient", lambda *args, **kwargs: _PassClient())  # noqa: ARG005
  for config in ("config-00", "config-01"):
    (tmp_path / config / "images").mkdir(parents=True)
    (tmp_path / config / "images" / "a.png").write_bytes(b"\x89PNG")
    record = ManifestRecord(image="images/a.png", library="matplotlib", labels={"has-title": Verdict.PASS})
    (tmp_path / config / "labels.jsonl").write_text(record.model_dump_json() + "\n", encoding="utf-8")
  substrate_out = tmp_path / "substrate.jsonl"
  exit_code = cli.main([str(tmp_path), "--substrate-out", str(substrate_out)])
  assert exit_code == cli.EXIT_OK
  out = capsys.readouterr().out
  assert "== overall ==" in out
  # Point at the parent directory; each config's labels.jsonl is discovered and labelled by its distinct absolute path.
  assert f"== {(tmp_path / 'config-00' / 'labels.jsonl').resolve()} ==" in out
  assert f"== {(tmp_path / 'config-01' / 'labels.jsonl').resolve()} ==" in out


def test_main_persists_substrate_when_the_manifest_path_is_non_ascii(
  monkeypatch: pytest.MonkeyPatch,
  tmp_path: Path,
) -> None:
  # The manifest name is now its absolute path, which can legitimately contain non-ASCII (e.g. a user's home dir).
  # The substrate must still persist - regression guard against an ASCII-only write. chr(0x00e9) is a lowercase e-acute.
  _set_credentials(monkeypatch)
  monkeypatch.setattr(cli, "OpenAiCompatClient", lambda *args, **kwargs: _PassClient())  # noqa: ARG005
  data_dir = tmp_path / f"config-{chr(0x00E9)}"
  (data_dir / "images").mkdir(parents=True)
  (data_dir / "images" / "a.png").write_bytes(b"\x89PNG")
  record = ManifestRecord(image="images/a.png", library="matplotlib", labels={"has-title": Verdict.PASS})
  (data_dir / "labels.jsonl").write_text(record.model_dump_json() + "\n", encoding="utf-8")
  substrate_out = tmp_path / "substrate.jsonl"
  assert cli.main([str(data_dir), "--substrate-out", str(substrate_out)]) == cli.EXIT_OK
  assert chr(0x00E9) in substrate_out.read_text(encoding="utf-8")


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


def test_format_report_renders_overall_and_macro() -> None:
  score = RuleScore("has-title", support=2, fail_support=1, error_count=0, precision=1.0, recall=1.0, accuracy=1.0)
  macro = MacroAverage(precision=1.0, recall=1.0, accuracy=1.0)
  board = Scoreboard(overall=Section("overall", (score,), macro), per_manifest=())
  report = cli.format_report(board)
  assert "== overall ==" in report
  assert "has-title" in report
  assert "macro" in report
