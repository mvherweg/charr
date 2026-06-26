"""Tests for the charr_datagen package metadata."""

import charr_datagen


def test_charr_datagen_package_exposes_a_semantic_version_string() -> None:
  assert charr_datagen.__version__ == "0.1.0"
