"""The on-disk dataset format: JSONL manifest records mapping each image to its per-rule ground-truth verdicts.

This is the write side of the published dataset contract (docs/adr/0011, docs/adr/0012). One JSON object per line, one
line per image; ``charr-eval`` reads the same shape independently (it does not import this package). The record reuses
charr's :class:`~charr.models.Verdict` and :class:`~charr.models.RuleId` so the labels speak the checker's own
vocabulary and validate uniformly with the rest of the codebase.
"""

import json
from collections.abc import Iterable
from pathlib import Path

from charr.models import RuleId, Verdict
from pydantic import BaseModel, ConfigDict


class ManifestRecord(BaseModel):
  """One image's ground-truth labels: the full per-rule verdict vector plus the library that rendered it.

  ``image`` is a path relative to the manifest file's own directory (docs/adr/0011). ``labels`` carries every rule the
  dataset covers, so the dataset is multi-label even while the MVP generator targets a single intended issue per chart
  (docs/adr/0016).
  """

  model_config = ConfigDict(extra="forbid")

  image: str
  library: str
  labels: dict[RuleId, Verdict]


def write_manifest(path: Path, records: Iterable[ManifestRecord]) -> None:
  """Write ``records`` to ``path`` as JSONL (one compact JSON object per line).

  :param path: Destination manifest file; its parent directory must already exist.
  :param records: The image records to serialize, in the order to write them.
  """
  with path.open("w", encoding="ascii") as handle:
    for record in records:
      handle.write(record.model_dump_json())
      handle.write("\n")


def read_manifest(path: Path) -> list[ManifestRecord]:
  """Parse a JSONL manifest, skipping blank lines and validating each record.

  :param path: The manifest file to read.
  :return: The parsed records in file order.
  :raises ValueError: If a non-blank line is not a valid :class:`ManifestRecord`.
  """
  records: list[ManifestRecord] = []
  for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
    if not line.strip():
      continue
    try:
      records.append(ManifestRecord.model_validate_json(line))
    except ValueError as exc:
      msg = f"{path}:{number}: invalid manifest record: {exc}"
      raise ValueError(msg) from exc
  return records


def labels_to_json(labels: dict[RuleId, Verdict]) -> str:
  """Render a label vector as deterministic, sorted-key JSON (handy for snapshots and logs).

  :param labels: A per-rule verdict mapping.
  :return: Sorted-key JSON with verdict values as strings.
  """
  return json.dumps({rule_id: verdict.value for rule_id, verdict in labels.items()}, sort_keys=True)
