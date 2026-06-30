"""Read a ``charr-eval`` substrate and shape it into display rows for the review UI.

The substrate is treated as a published contract (docs/adr/0022), so this module re-declares the record shape rather
than importing ``charr-eval``. Each ``(image, rule)`` substrate record becomes a :class:`ReviewRow` carrying the
expected and predicted verdicts, the recomputed confusion outcome (the substrate stores only the raw pair; docs/adr/0017
defines ``fail`` as the positive class and folds the error bucket in as a non-detection), and the model's rationale.
"""

from collections import Counter
from enum import StrEnum
from pathlib import Path, PurePosixPath

from charr.models import IMAGE_SUFFIXES, CharrError, RuleId, Verdict
from pydantic import BaseModel, ValidationError


class SubstrateRecord(BaseModel):
  """One ``(manifest, image, rule)`` row of a ``charr-eval`` substrate, the contract this tool consumes.

  Mirrors ``charr_eval.scoring.SubstrateRecord`` by construction (docs/adr/0022): ``predicted is None`` is the error
  bucket, ``raw`` is the model's rationale, and ``image`` is relative to the manifest's own directory.
  """

  manifest: str
  image: str
  rule_id: RuleId
  truth: Verdict
  predicted: Verdict | None
  raw: str | None = None
  error: str | None = None


class Outcome(StrEnum):
  """The per-row confusion outcome on the ``fail`` (violation) positive class, plus an error bucket."""

  TP = "TP"
  FP = "FP"
  FN = "FN"
  TN = "TN"
  ERROR = "ERROR"


class ReviewRow(BaseModel):
  """One ``(image, rule)`` judgement, ready to render: expectation, prediction, outcome, and rationale."""

  index: int
  manifest: str
  rule_id: RuleId
  truth: Verdict
  predicted: Verdict | None
  outcome: Outcome
  correct: bool
  rationale: str | None
  error: str | None
  image: str
  library: str | None
  polarity: str | None


class ReviewData(BaseModel):
  """Everything the UI needs from one substrate: the rows, an outcome summary, and any load-time warnings."""

  rows: list[ReviewRow]
  summary: dict[str, int]
  warnings: list[str]


def load_rows(substrate_path: Path, dataset_dir: Path) -> ReviewData:
  """Read a substrate JSONL and build the review rows, summary counts, and warnings.

  :param substrate_path: The ``charr-eval`` substrate JSONL to read.
  :param dataset_dir: The dataset root the substrate was scored against, used to check each image resolves.
  :return: The rows plus a per-outcome summary and any warnings (ambiguous substrate, missing images).
  :raises CharrError: If the substrate is missing records or has a malformed line.
  """
  records = _read_substrate(substrate_path)
  rows: list[ReviewRow] = []
  for index, record in enumerate(records):
    library, polarity = _parse_filename(record.image)
    rows.append(
      ReviewRow(
        index=index,
        manifest=record.manifest,
        rule_id=record.rule_id,
        truth=record.truth,
        predicted=record.predicted,
        outcome=classify(record.truth, record.predicted),
        correct=record.predicted is not None and record.predicted == record.truth,
        rationale=record.raw,
        error=record.error,
        image=record.image,
        library=library,
        polarity=polarity,
      ),
    )
  return ReviewData(rows=rows, summary=_summarize(rows), warnings=_detect_warnings(records, rows, dataset_dir))


def classify(truth: Verdict, predicted: Verdict | None) -> Outcome:
  """Classify one judgement on the ``fail`` positive class (docs/adr/0017).

  :param truth: The ground-truth verdict from the manifest label.
  :param predicted: The checker's verdict, or ``None`` for the error bucket.
  :return: ``ERROR`` when there is no prediction, else ``TP``/``FN`` when truth is ``fail`` and ``FP``/``TN`` otherwise.
  """
  if predicted is None:
    return Outcome.ERROR
  if truth is Verdict.FAIL:
    return Outcome.TP if predicted is Verdict.FAIL else Outcome.FN
  return Outcome.FP if predicted is Verdict.FAIL else Outcome.TN


def resolve_image_path(dataset_dir: Path, image: str) -> Path | None:
  """Resolve a record's manifest-relative image to a real file under ``dataset_dir``, or ``None``.

  Rejects paths that escape ``dataset_dir`` (traversal), non-image suffixes, and missing files, so a caller can serve
  the result without further validation.

  :param dataset_dir: The dataset root the image path is relative to.
  :param image: The manifest-relative image path from the substrate.
  :return: The resolved absolute path, or ``None`` when it escapes the root, is not an image, or does not exist.
  """
  root = dataset_dir.resolve()
  candidate = (root / image).resolve()
  if not candidate.is_relative_to(root):
    return None
  if candidate.suffix.lower() not in IMAGE_SUFFIXES:
    return None
  if not candidate.is_file():
    return None
  return candidate


def _read_substrate(path: Path) -> list[SubstrateRecord]:
  records: list[SubstrateRecord] = []
  with path.open(encoding="utf-8") as handle:
    for number, line in enumerate(handle, start=1):
      stripped = line.strip()
      if not stripped:
        continue
      try:
        records.append(SubstrateRecord.model_validate_json(stripped))
      except ValidationError as exc:
        msg = f"malformed substrate at {path}:{number}: {exc}"
        raise CharrError(msg) from exc
  if not records:
    msg = f"no records in substrate: {path}"
    raise CharrError(msg)
  return records


def _parse_filename(image: str) -> tuple[str | None, str | None]:
  """Best-effort ``(library, polarity)`` from a generated name ``NNNN-<rule>-<polarity>-<library>.png``.

  The rule id may contain hyphens, so parse positionally from the right; return ``(None, None)`` for any name that does
  not fit (e.g. a hand-authored dataset).
  """
  parts = PurePosixPath(image).stem.split("-")
  expected_min_parts = 4  # index, >=1 rule part, polarity, library
  if len(parts) < expected_min_parts or not parts[0].isdigit():
    return None, None
  return parts[-1], parts[-2]


def _summarize(rows: list[ReviewRow]) -> dict[str, int]:
  counts = Counter(row.outcome.value for row in rows)
  summary = {outcome.value: counts.get(outcome.value, 0) for outcome in Outcome}
  summary["total"] = len(rows)
  summary["mismatches"] = sum(1 for row in rows if not row.correct)
  return summary


def _detect_warnings(records: list[SubstrateRecord], rows: list[ReviewRow], dataset_dir: Path) -> list[str]:
  warnings: list[str] = []
  keys = Counter((record.manifest, record.image, record.rule_id) for record in records)
  collisions = sum(1 for count in keys.values() if count > 1)
  if collisions:
    warnings.append(
      f"{collisions} duplicate (manifest, image, rule) key(s): this substrate appears to span multiple datasets. "
      "Review one dataset/config per substrate (docs/adr/0022); image-to-rationale pairing may be wrong otherwise.",
    )
  missing = sum(1 for row in rows if resolve_image_path(dataset_dir, row.image) is None)
  if missing:
    warnings.append(f"{missing} of {len(rows)} referenced image(s) not found under {dataset_dir}.")
  return warnings
