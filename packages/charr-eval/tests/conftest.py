"""Shared fixtures for the charr-eval suite (all offline; no network).

Only fixtures live here. Fake ``LlmClient`` implementations live in the individual test modules that need them (as in
the charr suite), so nothing has to import this module by name under importlib mode.
"""

import base64
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest
from charr.models import ImageReport, Report, RuleId, RuleVerdict, Verdict
from charr_eval.manifest import ManifestRecord, resolve_image

# A real 1x1 PNG; only its existence matters here (nothing reads image bytes, the scorer never opens the files).
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


@pytest.fixture
def make_check_output(tmp_path: Path) -> Callable[[Path, Mapping[str, Mapping[RuleId, tuple[Verdict, str]]]], Path]:
  """Provide a helper that writes a saved ``charr check`` report (as produced by ``report.to_json()``).

  The report's image paths are the resolved absolute paths of the given manifest's images, so they join to the
  manifest's labels exactly as a real run would.

  :return: A function taking the manifest path and a ``{image_name -> {rule_id -> (verdict, rationale)}}`` table; it
    writes ``check.json`` under ``tmp_path`` and returns its path.
  """

  def _make(manifest: Path, verdicts_by_image: Mapping[str, Mapping[RuleId, tuple[Verdict, str]]]) -> Path:
    images = [
      ImageReport(
        image=str(resolve_image(manifest, ManifestRecord(image=f"images/{name}", library="matplotlib", labels={}))),
        verdicts=[RuleVerdict(rule_id=rid, verdict=v, rationale=r) for rid, (v, r) in per_rule.items()],
      )
      for name, per_rule in verdicts_by_image.items()
    ]
    check_output = tmp_path / "check.json"
    check_output.write_text(Report(images=images).to_json(), encoding="utf-8")
    return check_output

  return _make
