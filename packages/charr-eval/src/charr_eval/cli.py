"""Command-line entry point for the Charr evaluator.

Scores the checker against one or more labeled manifests and prints per-rule, per-manifest precision/recall/accuracy
plus an overall macro-average, while persisting the raw confusion substrate for failure analysis (docs/adr/0017). This
is the only module that touches argv, the environment, stdout/stderr, files, and the exit code. Exit codes: ``0``
evaluated successfully, ``2`` could not run (bad credentials, missing/malformed manifest).

Like the checker's real-endpoint runs, a real evaluation needs ``CHARR_LLM_*`` set and is for manual/dev use; the test
suite drives the same code path with a fake client and no network.
"""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import requests
from charr.config import Config, load_config, load_llm_settings
from charr.llm import LlmClient, OpenAiCompatClient
from charr.models import CharrError

from charr_eval.runner import evaluate_manifest
from charr_eval.scoring import MacroAverage, RuleScore, Scoreboard, Section, SubstrateRecord, build_scoreboard

EXIT_OK = 0
EXIT_CANNOT_RUN = 2

DEFAULT_SUBSTRATE_NAME = "charr-eval-substrate.jsonl"


def build_parser() -> argparse.ArgumentParser:
  """Build the argument parser: one or more manifests plus model/config/substrate options.

  :return: The configured argument parser.
  """
  parser = argparse.ArgumentParser(
    prog="charr-eval",
    description="Score the Charr checker against labeled chart manifests and report per-rule metrics.",
  )
  parser.add_argument("manifests", nargs="+", type=Path, metavar="MANIFEST", help="JSONL manifest file(s) to score.")
  parser.add_argument("--model", default=None, help="Override the CHARR_LLM_MODEL for this run.")
  parser.add_argument(
    "--config",
    type=Path,
    default=None,
    metavar="PATH",
    help="Use this checker config for every manifest instead of discovering one next to each.",
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
  """Evaluate the manifests and return the process exit code.

  :param argv: Command-line arguments; defaults to ``sys.argv`` when ``None``.
  :return: ``EXIT_OK`` (0) on success, ``EXIT_CANNOT_RUN`` (2) when the run cannot proceed.
  """
  args = build_parser().parse_args(argv)
  try:
    settings = load_llm_settings(os.environ)
    if args.model:
      settings = settings.model_copy(update={"model": args.model})
    with requests.Session() as session:
      client = OpenAiCompatClient(settings, session=session)
      records = _evaluate_all(args.manifests, client=client, config_path=args.config)
  except (CharrError, ValueError, OSError) as exc:
    sys.stderr.write(f"charr-eval: {exc}\n")
    return EXIT_CANNOT_RUN
  _persist_substrate(args.substrate_out, records)
  sys.stdout.write(format_report(build_scoreboard(records)))
  sys.stdout.write(f"\nWrote {len(records)} substrate record(s) to {args.substrate_out}\n")
  return EXIT_OK


def format_report(board: Scoreboard) -> str:
  """Render a scoreboard as an ASCII report: an overall section then one per manifest.

  :param board: The scored result.
  :return: The full report text (no trailing newline beyond the last line).
  """
  sections = [board.overall, *board.per_manifest]
  return "\n".join(_format_section(section) for section in sections)


def _evaluate_all(
  manifests: Sequence[Path],
  *,
  client: LlmClient,
  config_path: Path | None,
) -> list[SubstrateRecord]:
  records: list[SubstrateRecord] = []
  for manifest in manifests:
    if not manifest.is_file():
      msg = f"manifest not found: {manifest}"
      raise CharrError(msg)
    config = _config_for(manifest, config_path)
    records.extend(evaluate_manifest(manifest, client=client, config=config))
  return records


def _config_for(manifest: Path, config_path: Path | None) -> Config:
  if config_path is not None:
    return load_config(manifest.parent, config_path=config_path)
  return load_config(manifest.parent.resolve())


def _persist_substrate(path: Path, records: Sequence[SubstrateRecord]) -> None:
  with path.open("w", encoding="ascii") as handle:
    for record in records:
      handle.write(record.model_dump_json())
      handle.write("\n")


def _format_section(section: Section) -> str:
  header = f"== {section.name} =="
  columns = f"{'rule':<30} {'n':>4} {'fail':>5} {'err':>4} {'prec':>6} {'recall':>7} {'acc':>6}"
  rows = [_format_rule(score) for score in section.rule_scores]
  macro = _format_macro(section.macro)
  body = "\n".join([header, columns, *rows, macro]) if rows else f"{header}\n  (no records)"
  return body + "\n"


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
