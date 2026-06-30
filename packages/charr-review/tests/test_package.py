"""Smoke test: the package exposes its version."""

import charr_review


def test_version_is_exposed() -> None:
  assert charr_review.__version__ == "0.1.0"
