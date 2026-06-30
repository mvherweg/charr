"""Shared fixtures for the charr-review suite (all offline; no network, no LLM).

Only fixtures live here, as in the other suites, so nothing imports this module by name under importlib mode.
"""

import base64
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from charr_review.data import SubstrateRecord

# A real 1x1 PNG; only its existence and bytes matter (the server streams it back verbatim).
TINY_PNG = base64.b64decode(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
)


@pytest.fixture
def make_review(tmp_path: Path) -> Callable[[Sequence[SubstrateRecord]], tuple[Path, Path]]:
  """Provide a helper that writes a substrate JSONL plus its referenced images.

  :return: A function taking the substrate records; it writes the images under ``config-00/`` and the substrate
    alongside, returning ``(substrate_path, dataset_dir)``.
  """

  def _make(records: Sequence[SubstrateRecord]) -> tuple[Path, Path]:
    dataset_dir = tmp_path / "config-00"
    (dataset_dir / "images").mkdir(parents=True, exist_ok=True)
    for record in records:
      (dataset_dir / record.image).write_bytes(TINY_PNG)
    substrate = tmp_path / "substrate.jsonl"
    with substrate.open("w", encoding="ascii") as handle:
      for record in records:
        handle.write(record.model_dump_json())
        handle.write("\n")
    return substrate, dataset_dir

  return _make
