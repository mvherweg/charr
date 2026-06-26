"""Tests for the charr package metadata."""

import charr


def test_charr_package_exposes_a_semantic_version_string() -> None:
  assert charr.__version__ == "0.1.0"
