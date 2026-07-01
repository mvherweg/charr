"""Command-line entry point for the Charr review web app.

Loads a ``charr-eval`` substrate plus the dataset it was scored against and serves a local single-page app to browse the
results (docs/adr/0022, docs/adr/0023). This is the only module that touches argv, stdout/stderr, files, and the exit
code. Exit codes: ``0`` served (the server ran until interrupted), ``2`` could not run (missing substrate or dataset
dir, malformed substrate). It is read-only and makes no LLM calls.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from charr.models import CharrError

from charr_review.data import ReviewData, load_rows
from charr_review.server import serve

EXIT_OK = 0
EXIT_CANNOT_RUN = 2


def build_parser() -> argparse.ArgumentParser:
  """Build the argument parser: a substrate to review plus the dataset root and server options.

  :return: The configured argument parser.
  """
  parser = argparse.ArgumentParser(
    prog="charr-review",
    description="Browse charr-eval results: charts with expected vs predicted verdicts and the model's rationale.",
  )
  parser.add_argument("substrate", type=Path, metavar="SUBSTRATE", help="The charr-eval substrate JSONL to review.")
  parser.add_argument(
    "--dataset-dir",
    "-d",
    type=Path,
    required=True,
    metavar="DIR",
    help="The dataset root the substrate was scored against (resolves each record's manifest-relative image).",
  )
  parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1).")
  parser.add_argument("--port", type=int, default=8000, help="TCP port to bind (default: 8000).")
  parser.add_argument("--no-open", action="store_true", help="Do not open a browser window automatically.")
  return parser


def main(argv: Sequence[str] | None = None) -> int:
  """Load the substrate and serve the review UI; return the process exit code.

  :param argv: Command-line arguments; defaults to ``sys.argv`` when ``None``.
  :return: ``EXIT_OK`` (0) once the server stops, ``EXIT_CANNOT_RUN`` (2) when the run cannot proceed.
  """
  args = build_parser().parse_args(argv)
  try:
    data = _load(args.substrate, args.dataset_dir)
  except (CharrError, OSError) as exc:
    # Only expected operational failures are reported as "cannot run": CharrError (missing substrate/dataset dir,
    # malformed substrate) and OSError (unreadable files). Any other exception is a programming fault and must surface
    # as a crash rather than be masked as exit 2.
    sys.stderr.write(f"charr-review: {exc}\n")
    return EXIT_CANNOT_RUN
  for warning in data.warnings:
    sys.stderr.write(f"charr-review: warning: {warning}\n")
  serve(data, args.dataset_dir, host=args.host, port=args.port, open_browser=not args.no_open)
  return EXIT_OK


def _load(substrate: Path, dataset_dir: Path) -> ReviewData:
  if not substrate.is_file():
    msg = f"substrate not found: {substrate}"
    raise CharrError(msg)
  if not dataset_dir.is_dir():
    msg = f"dataset dir not found: {dataset_dir}"
    raise CharrError(msg)
  return load_rows(substrate, dataset_dir)
