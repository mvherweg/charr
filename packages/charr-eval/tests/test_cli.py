"""Tests for the evaluator CLI: the offline end-to-end path scoring a saved check output, and the report formatter."""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest
from charr.models import ImageReport, Report, RuleId, RuleVerdict, Verdict
from charr_eval import cli
from charr_eval.manifest import ManifestRecord, resolve_image
from charr_eval.scoring import MacroAverage, RuleScore, Scoreboard, Section

_CheckOutput = Callable[[Path, Mapping[str, Mapping[RuleId, tuple[Verdict, str]]]], Path]


def _record(image: str, labels: Mapping[RuleId, Verdict]) -> ManifestRecord:
  return ManifestRecord(image=image, library="matplotlib", labels=dict(labels))


def test_main_scores_a_manifest_end_to_end_against_a_saved_check_output(
  capsys: pytest.CaptureFixture[str],
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
  make_check_output: _CheckOutput,
  tmp_path: Path,
) -> None:
  manifest = make_dataset([_record("images/a.png", {"has-title": Verdict.PASS})])
  check_output = make_check_output(manifest, {"a.png": {"has-title": (Verdict.PASS, "ok")}})
  substrate_out = tmp_path / "substrate.jsonl"
  exit_code = cli.main([str(check_output), str(manifest), "--substrate-out", str(substrate_out)])
  assert exit_code == cli.EXIT_OK
  assert "== overall ==" in capsys.readouterr().out
  assert substrate_out.is_file()
  assert substrate_out.read_text(encoding="utf-8").strip()


def test_main_discovers_manifests_under_a_directory_and_names_them_by_absolute_path(
  capsys: pytest.CaptureFixture[str],
  tmp_path: Path,
) -> None:
  images: list[ImageReport] = []
  for config in ("config-00", "config-01"):
    (tmp_path / config / "images").mkdir(parents=True)
    (tmp_path / config / "images" / "a.png").write_bytes(b"\x89PNG")
    record = _record("images/a.png", {"has-title": Verdict.PASS})
    (tmp_path / config / "labels.jsonl").write_text(record.model_dump_json() + "\n", encoding="utf-8")
    image_path = resolve_image(tmp_path / config / "labels.jsonl", record)
    images.append(
      ImageReport(
        image=str(image_path), verdicts=[RuleVerdict(rule_id="has-title", verdict=Verdict.PASS, rationale="ok")]
      )
    )
  check_output = tmp_path / "check.json"
  check_output.write_text(Report(images=images).to_json(), encoding="utf-8")
  substrate_out = tmp_path / "substrate.jsonl"
  exit_code = cli.main([str(check_output), str(tmp_path), "--substrate-out", str(substrate_out)])
  assert exit_code == cli.EXIT_OK
  out = capsys.readouterr().out
  assert "== overall ==" in out
  # Point at the parent directory; each config's labels.jsonl is discovered and labelled by its distinct absolute path.
  assert f"== {(tmp_path / 'config-00' / 'labels.jsonl').resolve()} ==" in out
  assert f"== {(tmp_path / 'config-01' / 'labels.jsonl').resolve()} ==" in out


def test_main_persists_substrate_when_the_manifest_path_is_non_ascii(
  make_check_output: _CheckOutput,
  tmp_path: Path,
) -> None:
  # The manifest name is now its absolute path, which can legitimately contain non-ASCII (e.g. a user's home dir).
  # The substrate must still persist - regression guard against an ASCII-only write. chr(0x00e9) is a lowercase e-acute.
  data_dir = tmp_path / f"config-{chr(0x00E9)}"
  (data_dir / "images").mkdir(parents=True)
  (data_dir / "images" / "a.png").write_bytes(b"\x89PNG")
  record = _record("images/a.png", {"has-title": Verdict.PASS})
  manifest = data_dir / "labels.jsonl"
  manifest.write_text(record.model_dump_json() + "\n", encoding="utf-8")
  check_output = make_check_output(manifest, {"a.png": {"has-title": (Verdict.PASS, "ok")}})
  substrate_out = tmp_path / "substrate.jsonl"
  assert cli.main([str(check_output), str(manifest), "--substrate-out", str(substrate_out)]) == cli.EXIT_OK
  assert chr(0x00E9) in substrate_out.read_text(encoding="utf-8")


def test_main_persists_a_non_ascii_rationale_as_utf8(
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
  make_check_output: _CheckOutput,
  tmp_path: Path,
) -> None:
  # chr(0x2019) is U+2019 RIGHT SINGLE QUOTATION MARK: the kind of non-ASCII a real model emits in prose; it arrives
  # via the saved check output and must round-trip through the substrate as UTF-8.
  manifest = make_dataset([_record("images/a.png", {"has-title": Verdict.PASS})])
  rationale = f"the title isn{chr(0x2019)}t centred"
  check_output = make_check_output(manifest, {"a.png": {"has-title": (Verdict.PASS, rationale)}})
  substrate_out = tmp_path / "substrate.jsonl"
  exit_code = cli.main([str(check_output), str(manifest), "--substrate-out", str(substrate_out)])
  assert exit_code == cli.EXIT_OK
  assert chr(0x2019) in substrate_out.read_text(encoding="utf-8")


def test_main_returns_cannot_run_for_a_missing_manifest(
  make_check_output: _CheckOutput,
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
  tmp_path: Path,
) -> None:
  manifest = make_dataset([_record("images/a.png", {"has-title": Verdict.PASS})])
  check_output = make_check_output(manifest, {"a.png": {"has-title": (Verdict.PASS, "ok")}})
  assert cli.main([str(check_output), str(tmp_path / "nope.jsonl")]) == cli.EXIT_CANNOT_RUN


def test_main_returns_cannot_run_for_a_malformed_manifest(
  make_check_output: _CheckOutput,
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
  tmp_path: Path,
) -> None:
  manifest = make_dataset([_record("images/a.png", {"has-title": Verdict.PASS})])
  check_output = make_check_output(manifest, {"a.png": {"has-title": (Verdict.PASS, "ok")}})
  bad = tmp_path / "labels.jsonl"
  bad.write_text("not json\n", encoding="utf-8")
  assert cli.main([str(check_output), str(bad)]) == cli.EXIT_CANNOT_RUN


def test_main_returns_cannot_run_for_a_malformed_check_output(
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
  tmp_path: Path,
) -> None:
  manifest = make_dataset([_record("images/a.png", {"has-title": Verdict.PASS})])
  bad_check = tmp_path / "check.json"
  bad_check.write_text("not json", encoding="utf-8")
  assert cli.main([str(bad_check), str(manifest)]) == cli.EXIT_CANNOT_RUN


def test_main_returns_cannot_run_when_a_prediction_matches_no_manifest_image(
  capsys: pytest.CaptureFixture[str],
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
  make_check_output: _CheckOutput,
) -> None:
  # A prediction for an image no manifest references means the two inputs do not correspond: hard error, exit 2.
  manifest = make_dataset([_record("images/a.png", {"has-title": Verdict.PASS})])
  check_output = make_check_output(
    manifest,
    {"a.png": {"has-title": (Verdict.PASS, "ok")}, "stray.png": {"has-title": (Verdict.PASS, "ok")}},
  )
  assert cli.main([str(check_output), str(manifest)]) == cli.EXIT_CANNOT_RUN
  assert "stray.png" in capsys.readouterr().err


def test_main_folds_an_unmatched_manifest_image_into_the_error_bucket(
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
  tmp_path: Path,
) -> None:
  # The opposite direction: a manifest image with no prediction is a per-cell gap, not a fatal mismatch - exit 0 with
  # an error-bucket record, never dropped (docs/adr/0017).
  manifest = make_dataset([_record("images/a.png", {"has-title": Verdict.PASS})])
  empty_check = tmp_path / "check.json"
  empty_check.write_text(Report(images=[]).to_json(), encoding="utf-8")
  substrate_out = tmp_path / "substrate.jsonl"
  assert cli.main([str(empty_check), str(manifest), "--substrate-out", str(substrate_out)]) == cli.EXIT_OK
  assert "no prediction for image" in substrate_out.read_text(encoding="utf-8")


def test_main_allows_one_prediction_to_cover_multiple_manifests(
  tmp_path: Path,
) -> None:
  # Two manifests referencing the same image, one prediction entry: consumed is a union, so the image is not a stray.
  shared = tmp_path / "images" / "a.png"
  shared.parent.mkdir(parents=True)
  shared.write_bytes(b"\x89PNG")
  record = _record("../images/a.png", {"has-title": Verdict.PASS})
  manifests = []
  for name in ("m0", "m1"):
    (tmp_path / name).mkdir()
    manifest = tmp_path / name / "labels.jsonl"
    manifest.write_text(record.model_dump_json() + "\n", encoding="utf-8")
    manifests.append(manifest)
  check_output = tmp_path / "check.json"
  check_output.write_text(
    Report(
      images=[
        ImageReport(
          image=str(shared.resolve()), verdicts=[RuleVerdict(rule_id="has-title", verdict=Verdict.PASS, rationale="ok")]
        )
      ]
    ).to_json(),
    encoding="utf-8",
  )
  substrate_out = tmp_path / "substrate.jsonl"
  exit_code = cli.main([str(check_output), *(str(m) for m in manifests), "--substrate-out", str(substrate_out)])
  assert exit_code == cli.EXIT_OK


def test_main_does_not_mask_an_unexpected_error_as_cannot_run(
  monkeypatch: pytest.MonkeyPatch,
  make_dataset: Callable[[Sequence[ManifestRecord]], Path],
  make_check_output: _CheckOutput,
) -> None:
  # A programming fault (here a stand-in ValueError from persistence, as a UnicodeEncodeError once was) must crash,
  # not be swallowed into exit 2 - otherwise real bugs masquerade as "cannot run".
  def _boom(*args: object, **kwargs: object) -> None:  # noqa: ARG001
    msg = "unexpected fault"
    raise ValueError(msg)

  monkeypatch.setattr(cli, "_persist_substrate", _boom)
  manifest = make_dataset([_record("images/a.png", {"has-title": Verdict.PASS})])
  check_output = make_check_output(manifest, {"a.png": {"has-title": (Verdict.PASS, "ok")}})
  with pytest.raises(ValueError, match="unexpected fault"):
    cli.main([str(check_output), str(manifest)])


def test_format_report_renders_overall_and_macro() -> None:
  score = RuleScore("has-title", support=2, fail_support=1, error_count=0, precision=1.0, recall=1.0, accuracy=1.0)
  macro = MacroAverage(precision=1.0, recall=1.0, accuracy=1.0)
  board = Scoreboard(overall=Section("overall", (score,), macro), per_manifest=())
  report = cli.format_report(board)
  assert "== overall ==" in report
  assert "has-title" in report
  assert "macro" in report
