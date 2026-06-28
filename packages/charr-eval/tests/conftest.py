"""Shared fixtures for the charr-eval suite (all offline; no network).

Only fixtures live here. Fake ``LlmClient`` implementations live in the individual test modules that need them (as in
the charr suite), so nothing has to import this module by name under importlib mode.
"""

import base64
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from charr_eval.manifest import ManifestRecord

# A real 1x1 PNG; only its existence matters here (the fake clients never read image bytes).
TINY_PNG = base64.b64decode(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
)


@pytest.fixture
def make_dataset(tmp_path: Path) -> Callable[[Sequence[ManifestRecord]], Path]:
  """Provide a helper that writes a manifest plus its referenced image files and returns the manifest path.

  :return: A function taking the records to write; it creates ``images/`` and the ``labels.jsonl`` under ``tmp_path``.
  """

  def _make(records: Sequence[ManifestRecord]) -> Path:
    (tmp_path / "images").mkdir(exist_ok=True)
    for record in records:
      (tmp_path / record.image).write_bytes(TINY_PNG)
    manifest = tmp_path / "labels.jsonl"
    with manifest.open("w", encoding="ascii") as handle:
      for record in records:
        handle.write(record.model_dump_json())
        handle.write("\n")
    return manifest

  return _make
