"""Shared fixtures for the charr test suite (all offline; no network).

Fake ``LlmClient`` implementations live in the individual test modules that need them, fully typed; this module only
provides the shared image bytes and temp-file helpers.
"""

import base64
from collections.abc import Callable
from pathlib import Path

import pytest

# A real 1x1 PNG. encode_image_data_url only base64-encodes the bytes, so any valid file content works.
TINY_PNG = base64.b64decode(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
)


@pytest.fixture
def make_image() -> Callable[[Path], Path]:
  """Provide a helper that writes the tiny PNG bytes to a path.

  :return: A function that writes the bytes to its path argument and returns it (the suffix sets the MIME; content is
    irrelevant for our code).
  """

  def _make(path: Path) -> Path:
    path.write_bytes(TINY_PNG)
    return path

  return _make


@pytest.fixture
def png_file(tmp_path: Path) -> Path:
  """Write a tiny valid PNG named ``chart.png`` into the test's temp directory.

  :param tmp_path: The pytest-provided temporary directory.
  :return: Path to the written ``chart.png``.
  """
  path = tmp_path / "chart.png"
  path.write_bytes(TINY_PNG)
  return path
