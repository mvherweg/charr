"""Command-line entry point for the Charr data generator.

A single ``generate`` subcommand that writes a labeled dataset (images + JSONL manifest + checker config + run
metadata) under ``--out``. This is the only module that touches argv, stdout/stderr, and the process exit code. Exit
codes: ``0`` generated successfully, ``2`` could not run (bad library pin, or under-budget under ``--strict-coverage``).
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from charr.models import CharrError

from charr_datagen.generate import (
  CONFIG_NAME,
  MANIFEST_NAME,
  META_NAME,
  GenerationResult,
  generate,
)
from charr_datagen.rendering import ALL_LIBRARIES

EXIT_OK = 0
EXIT_CANNOT_RUN = 2


def build_parser() -> argparse.ArgumentParser:
  """Build the argument parser: a single ``generate`` subcommand.

  :return: The configured argument parser.
  """
  parser = argparse.ArgumentParser(
    prog="charr-datagen",
    description="Generate synthetic charts with ground-truth per-rule labels for evaluating the Charr checker.",
  )
  subparsers = parser.add_subparsers(dest="command", required=True)
  gen = subparsers.add_parser("generate", help="Render a labeled dataset under --out.")
  gen.add_argument("--out", type=Path, required=True, metavar="DIR", help="Directory to write the dataset into.")
  gen.add_argument("--seed", type=int, default=0, help="Base seed; a run is reproducible per active library set.")
  gen.add_argument(
    "--samples",
    type=int,
    default=None,
    metavar="N",
    help="Total number of cases to generate (default: one per (rule, polarity) cell).",
  )
  gen.add_argument(
    "--libraries",
    nargs="+",
    default=None,
    metavar="LIB",
    choices=ALL_LIBRARIES,
    help="Pin the rendering libraries (default: matplotlib, seaborn, and plotly when usable).",
  )
  gen.add_argument(
    "--strict-coverage",
    action="store_true",
    help="Error instead of warning when --samples cannot cover every cell.",
  )
  return parser


def main(argv: Sequence[str] | None = None) -> int:
  """Run the generator and return the process exit code.

  :param argv: Command-line arguments; defaults to ``sys.argv`` when ``None``.
  :return: ``EXIT_OK`` (0) on success, ``EXIT_CANNOT_RUN`` (2) when the run cannot proceed.
  """
  args = build_parser().parse_args(argv)
  try:
    result = generate(
      args.out,
      samples=args.samples,
      seed=args.seed,
      libraries=args.libraries,
      strict_coverage=args.strict_coverage,
    )
  except CharrError as exc:
    sys.stderr.write(f"charr-datagen: {exc}\n")
    return EXIT_CANNOT_RUN
  _report(result)
  return EXIT_OK


def _report(result: GenerationResult) -> None:
  """Print a short human summary of a completed run to stdout (warnings included)."""
  for message in result.messages:
    sys.stderr.write(f"charr-datagen: {message}\n")
  lines = [
    f"Wrote {result.image_count} image(s) to {result.out_dir}",
    f"  libraries: {', '.join(result.libraries)}",
    f"  manifest:  {result.out_dir / MANIFEST_NAME}",
    f"  config:    {result.out_dir / CONFIG_NAME}",
    f"  metadata:  {result.out_dir / META_NAME}",
  ]
  if result.uncovered:
    lines.append(f"  uncovered: {len(result.uncovered)} cell(s) (see metadata)")
  sys.stdout.write("\n".join(lines) + "\n")
