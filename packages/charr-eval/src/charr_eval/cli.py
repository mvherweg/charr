"""Command-line entry point for the Charr evaluator.

Scores a saved ``charr check`` output against one or more labeled manifests and prints per-rule, per-manifest
precision/recall/accuracy plus an overall macro-average, while persisting the raw confusion substrate for failure
analysis (docs/adr/0017). The evaluator is a pure scorer (docs/adr/0025): it never runs the checker, so it needs no
credentials and no network - produce the predictions once with ``charr check`` and score them here.

This is the only module that touches argv, stdout/stderr, files, and the exit code. Exit codes: ``0`` evaluated
successfully, ``2`` could not run (missing/malformed manifest or check output, or a prediction that matches no
manifest image - meaning the two inputs do not correspond).
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from charr.models import CharrError

from charr_eval.manifest import discover_manifests, manifest_display_name
from charr_eval.predictions import PredictionsByImage, load_predictions
from charr_eval.runner import evaluate_manifest
from charr_eval.scoring import MacroAverage, RuleScore, Scoreboard, Section, SubstrateRecord, build_scoreboard

EXIT_OK = 0
EXIT_CANNOT_RUN = 2

DEFAULT_SUBSTRATE_NAME = "charr-eval-substrate.jsonl"


def build_parser() -> argparse.ArgumentParser:
  """Build the argument parser: the saved check output, one or more manifests, and the substrate option.

  :return: The configured argument parser.
  """
  parser = argparse.ArgumentParser(
    prog="charr-eval",
    description="Score a saved 'charr check' output against labeled chart manifests and report per-rule metrics.",
  )
  parser.add_argument(
    "predictions",
    type=Path,
    metavar="CHECK_OUTPUT",
    help="A saved 'charr check' JSON report (the predictions to score).",
  )
  parser.add_argument(
    "manifests",
    nargs="+",
    type=Path,
    metavar="PATH",
    help="Manifest file(s), or directories to search recursively for labels.jsonl.",
  )
  parser.add_argument(
    "--substrate-out",
    type=Path,
    default=Path(DEFAULT_SUBSTRATE_NAME),
    metavar="PATH",
    help=f"Where to persist the raw confusion substrate as JSONL (default: ./{DEFAULT_SUBSTRATE_NAME}).",
  )
  return parser


def main(argv: Sequence[str] | None = None) -> int:
  """Evaluate the manifests against the saved predictions and return the process exit code.

  :param argv: Command-line arguments; defaults to ``sys.argv`` when ``None``.
  :return: ``EXIT_OK`` (0) on success, ``EXIT_CANNOT_RUN`` (2) when the run cannot proceed.
  """
  args = build_parser().parse_args(argv)
  try:
    predictions = load_predictions(args.predictions)
    records, consumed = _evaluate_all(args.manifests, predictions=predictions)
    if stray := _unmatched_predictions(predictions, consumed):
      lines = "".join(f"  {key}\n" for key in stray)
      sys.stderr.write(f"charr-eval: predictions with no matching manifest image:\n{lines}")
      return EXIT_CANNOT_RUN
    _persist_substrate(args.substrate_out, records)
  except (CharrError, OSError) as exc:
    # Only expected operational failures are reported as "cannot run": CharrError (malformed manifest or check output,
    # a stray prediction) and OSError (unreadable/unwritable files). A bare ValueError or any other exception is a
    # programming fault and must surface as a crash, not be masked as exit 2 (this is what once hid a UnicodeEncodeError
    # here).
    sys.stderr.write(f"charr-eval: {exc}\n")
    return EXIT_CANNOT_RUN
  sys.stdout.write(format_report(build_scoreboard(records)) + "\n")
  sys.stdout.write(f"\nWrote {len(records)} substrate record(s) to {args.substrate_out}\n")
  return EXIT_OK


def format_report(board: Scoreboard) -> str:
  """Render a scoreboard as an ASCII report: an overall section then one per manifest.

  :param board: The scored result.
  :return: The full report text, sections separated by a blank line, with no trailing newline.
  """
  sections = [board.overall, *board.per_manifest]
  return "\n\n".join(_format_section(section) for section in sections)


def _evaluate_all(
  manifests: Sequence[Path],
  *,
  predictions: PredictionsByImage,
) -> tuple[list[SubstrateRecord], set[Path]]:
  records: list[SubstrateRecord] = []
  consumed: set[Path] = set()
  for manifest in discover_manifests(manifests):
    name = manifest_display_name(manifest)
    manifest_records, manifest_consumed = evaluate_manifest(manifest, name=name, predictions=predictions)
    records.extend(manifest_records)
    consumed |= manifest_consumed
  return records, consumed


def _unmatched_predictions(predictions: PredictionsByImage, consumed: set[Path]) -> list[Path]:
  """Return the prediction image keys matched by no manifest, sorted for a deterministic report.

  A prediction may legitimately be matched by more than one manifest (overlapping datasets); ``consumed`` is the union
  across all manifests, so such an image is never flagged. A key left over means the predictions and the manifests do
  not correspond.
  """
  return sorted(key for key in predictions if key not in consumed)


def _persist_substrate(path: Path, records: Sequence[SubstrateRecord]) -> None:
  with path.open("w", encoding="utf-8") as handle:
    for record in records:
      handle.write(record.model_dump_json())
      handle.write("\n")


def _format_section(section: Section) -> str:
  header = f"== {section.name} =="
  columns = f"{'rule':<30} {'n':>4} {'fail':>5} {'err':>4} {'prec':>6} {'recall':>7} {'acc':>6}"
  rows = [_format_rule(score) for score in section.rule_scores]
  macro = _format_macro(section.macro)
  if not rows:
    return f"{header}\n  (no records)"
  return "\n".join([header, columns, *rows, macro])


def _format_rule(score: RuleScore) -> str:
  return (
    f"{score.rule_id:<30} {score.support:>4} {score.fail_support:>5} {score.error_count:>4} "
    f"{_pct(score.precision):>6} {_pct(score.recall):>7} {_pct(score.accuracy):>6}"
  )


def _format_macro(macro: MacroAverage) -> str:
  cells = f"{_pct(macro.precision):>6} {_pct(macro.recall):>7} {_pct(macro.accuracy):>6}"
  return f"{'macro':<30} {'':>4} {'':>5} {'':>4} {cells}"


def _pct(value: float | None) -> str:
  return "-" if value is None else f"{value:.2f}"
