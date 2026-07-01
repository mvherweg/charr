"""Reading the labeled-dataset manifest format that ``charr-eval`` scores against.

This is the read side of the published dataset contract (docs/adr/0011, docs/adr/0012): JSONL, one record per image,
image paths relative to the manifest's own directory. ``charr-eval`` deliberately does not import ``charr-datagen`` (it
must score any dataset in this format, generated or hand-curated), so it carries its own record model. The model reuses
charr's :class:`~charr.models.Verdict` and :class:`~charr.models.RuleId`, keeping the two readers in lockstep on the
vocabulary even though the struct is duplicated by design.
"""

from collections.abc import Sequence
from pathlib import Path

from charr.models import CharrError, RuleId, Verdict
from pydantic import BaseModel, ConfigDict, ValidationError


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
  :raises CharrError: If a non-blank line is not a valid :class:`ManifestRecord` (a dataset error, distinct from a
    programming fault, so the CLI can report it cleanly rather than crash).
  """
  records: list[ManifestRecord] = []
  for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
    if not line.strip():
      continue
    try:
      records.append(ManifestRecord.model_validate_json(line))
    except ValidationError as exc:
      msg = f"{path}:{number}: invalid manifest record: {exc}"
      raise CharrError(msg) from exc
  return records


def resolve_image(manifest_path: Path, record: ManifestRecord) -> Path:
  """Resolve a record's image path relative to its manifest's directory.

  :param manifest_path: Path to the manifest file the record came from.
  :param record: The record whose ``image`` to resolve.
  :return: The absolute image path (not checked for existence here).
  """
  return (manifest_path.parent / record.image).resolve()


def discover_manifests(paths: Sequence[Path]) -> list[Path]:
  """Expand the command-line path arguments into the concrete list of manifest files to score.

  Each argument is either a manifest **file** (taken as-is; an explicitly named file need not be called
  ``labels.jsonl``) or a **directory**, which is searched recursively for ``labels.jsonl`` files. Duplicates - for
  example a directory and a file it contains, both passed - are removed while keeping first-seen order.

  :param paths: The path arguments as given on the command line (files and/or directories).
  :return: The manifest files to score, deduplicated and in a deterministic order.
  :raises CharrError: If an argument is neither an existing file nor a directory, or a directory contains no
    ``labels.jsonl``.
  """
  manifests: list[Path] = []
  seen: set[Path] = set()
  for path in paths:
    if path.is_dir():
      # Filter to files: rglob matches by name, so a directory literally named labels.jsonl would otherwise be
      # returned and then fail with IsADirectoryError when read.
      candidates = sorted(p for p in path.rglob("labels.jsonl") if p.is_file())
      if not candidates:
        msg = f"no labels.jsonl manifests under: {path}"
        raise CharrError(msg)
    elif path.is_file():
      candidates = [path]
    else:
      msg = f"manifest path not found: {path}"
      raise CharrError(msg)
    for manifest in candidates:
      key = manifest.resolve()
      if key not in seen:
        seen.add(key)
        manifests.append(manifest)
  return manifests


def manifest_display_name(path: Path) -> str:
  """Return the label a manifest carries throughout the results: its canonical absolute path.

  The absolute path is unambiguous and collision-free, so distinct datasets never merge in the per-manifest report even
  when they all use the conventional ``labels.jsonl`` filename. This is deliberately a plain, swappable naming policy -
  a friendlier provider-declared name is future work (the manifest format carries no name of its own today).

  :param path: A manifest file path.
  :return: The resolved absolute path, as a string.
  """
  return str(path.resolve())
