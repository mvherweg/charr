"""Command-line entry point for the Charr chart checker.

Wires config + credential loading, image discovery, and the LLM client into a single ``check`` run. This is the only
module that touches argv, the environment, stdout/stderr, and the process exit code. Exit codes: ``0`` ran with no
failing rule, ``1`` at least one rule failed (the CI gate), ``2`` could not run (bad config/credentials, no inputs
matched, or an LLM/backend failure).
"""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import requests

from charr.checker import run_check
from charr.config import load_config, load_llm_settings
from charr.discovery import discover_images
from charr.llm import OpenAiCompatClient
from charr.models import CharrError

EXIT_OK = 0
EXIT_RULE_FAILED = 1
EXIT_CANNOT_RUN = 2


def build_parser() -> argparse.ArgumentParser:
  """Build the argument parser: a single ``check`` subcommand with inputs and rule-selection overrides.

  :return: The configured argument parser.
  """
  parser = argparse.ArgumentParser(
    prog="charr",
    description="Lint chart images against a rule set using a (local) LLM, and emit a JSON report.",
  )
  subparsers = parser.add_subparsers(dest="command", required=True)
  check = subparsers.add_parser("check", help="Check chart images and emit a JSON report on stdout.")
  check.add_argument("inputs", nargs="+", help="Image files, globs, or directories to check.")
  check.add_argument(
    "--enable",
    action="append",
    default=[],
    metavar="RULE",
    help="Enable a rule on top of config (repeatable).",
  )
  check.add_argument(
    "--disable",
    action="append",
    default=[],
    metavar="RULE",
    help="Disable a rule, overriding config (repeatable).",
  )
  check.add_argument(
    "--config",
    type=Path,
    default=None,
    metavar="PATH",
    help="Use this config file instead of discovering one.",
  )
  return parser


def main(argv: Sequence[str] | None = None) -> int:
  """Run a check and return the process exit code.

  :param argv: Command-line arguments to parse; defaults to ``sys.argv`` when ``None``.
  :return: ``EXIT_OK`` (0), ``EXIT_RULE_FAILED`` (1), or ``EXIT_CANNOT_RUN`` (2); see the module docstring.
  """
  args = build_parser().parse_args(argv)
  cwd = Path.cwd()
  try:
    config = load_config(cwd, enable=args.enable, disable=args.disable, config_path=args.config)
    settings = load_llm_settings(os.environ)
    images = discover_images(args.inputs, cwd=cwd)
    with requests.Session() as session:
      client = OpenAiCompatClient(settings, session=session)
      report = run_check(images, config, client)
  except CharrError as exc:
    sys.stderr.write(f"charr: {exc}\n")
    return EXIT_CANNOT_RUN
  sys.stdout.write(f"{report.to_json()}\n")
  return EXIT_OK if report.ok else EXIT_RULE_FAILED
