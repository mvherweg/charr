"""Reading the labeled-dataset manifest format that ``charr-eval`` scores against.

This is the read side of the published dataset contract (docs/adr/0011, docs/adr/0012): JSONL, one record per image,
image paths relative to the manifest's own directory. ``charr-eval`` deliberately does not import ``charr-datagen`` (it
must score any dataset in this format, generated or hand-curated), so it carries its own record model. The model reuses
charr's :class:`~charr.models.Verdict` and :class:`~charr.models.RuleId`, keeping the two readers in lockstep on the
vocabulary even though the struct is duplicated by design.
"""

from pathlib import Path

from charr.models import RuleId, Verdict
from pydantic import BaseModel, ConfigDict


class ManifestRecord(BaseModel):
  """One image's ground-truth labels: the per-rule verdict vector plus the library that rendered it."""

  model_config = ConfigDict(extra="forbid")

  image: str
  library: str
  labels: dict[RuleId, Verdict]


def read_manifest(path: Path) -> list[ManifestRecord]:
  """Parse a JSONL manifest, skipping blank lines and validating each record.

  :param path: The manifest file to read.
  :return: The records in file order.
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


def resolve_image(manifest_path: Path, record: ManifestRecord) -> Path:
  """Resolve a record's image path relative to its manifest's directory.

  :param manifest_path: Path to the manifest file the record came from.
  :param record: The record whose ``image`` to resolve.
  :return: The absolute image path (not checked for existence here).
  """
  return (manifest_path.parent / record.image).resolve()
