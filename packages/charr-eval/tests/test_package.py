"""Tests for the charr_eval package metadata."""

import charr_eval


def test_charr_eval_package_exposes_a_semantic_version_string() -> None:
  assert charr_eval.__version__ == "0.1.0"
