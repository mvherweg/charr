"""Join a manifest's ground-truth labels to a saved check output and fold each per-rule outcome into a substrate record.

This is the score side of the run/score split (docs/adr/0025): instead of driving the checker, the evaluator reads the
predictions produced by an earlier ``charr check`` run (see :mod:`charr_eval.predictions`) and matches them to the
manifest's labels image by image. An image the manifest expects but the predictions do not cover degrades to an
``error`` bucket for that image's rules rather than aborting the whole evaluation. The captured raw rationale is kept on
each record for failure analysis.
"""

from pathlib import Path

from charr.models import RuleId, Verdict

from charr_eval.manifest import ManifestRecord, read_manifest, resolve_image
from charr_eval.predictions import PredictionsByImage
from charr_eval.scoring import SubstrateRecord


def evaluate_manifest(
  manifest_path: Path,
  *,
  name: str,
  predictions: PredictionsByImage,
) -> tuple[list[SubstrateRecord], set[Path]]:
  """Score ``manifest_path``'s labels against ``predictions`` and return the substrate records plus consumed keys.

  :param manifest_path: The manifest to evaluate.
  :param name: The label to stamp on every record as this manifest's identity in the results; the caller derives it
    (see :func:`charr_eval.manifest.manifest_display_name`), keeping naming policy out of the runner.
  :param predictions: The saved check output, indexed by resolved image path (see
    :func:`charr_eval.predictions.load_predictions`).
  :return: A pair of (one :class:`SubstrateRecord` per ``(image, rule)`` in the manifest, the set of prediction keys
    this manifest matched). The caller unions the consumed keys across manifests to spot predictions matched by none.
  :raises CharrError: If the manifest itself is malformed (a dataset error, not a checker error).
  """
  records: list[SubstrateRecord] = []
  consumed: set[Path] = set()
  for record in read_manifest(manifest_path):
    key = resolve_image(manifest_path, record)
    predicted = predictions.get(key)
    if predicted is None:
      records.extend(_image_records(name, record, {}, f"no prediction for image: {key}"))
    else:
      consumed.add(key)
      records.extend(_image_records(name, record, predicted, None))
  return records, consumed


def _image_records(
  manifest_name: str,
  record: ManifestRecord,
  predicted: dict[RuleId, tuple[Verdict, str]],
  error: str | None,
) -> list[SubstrateRecord]:
  """Fold one image's outcome into per-rule substrate records, mapping a missing prediction to the error bucket."""
  out: list[SubstrateRecord] = []
  for rule_id, truth in record.labels.items():
    if error is not None:
      predicted_verdict, raw, rule_error = None, None, error
    elif (found := predicted.get(rule_id)) is None:
      predicted_verdict, raw, rule_error = None, None, "rule not evaluated by the checker (disabled?)"
    else:
      verdict, rationale = found
      predicted_verdict, raw, rule_error = verdict, rationale, None
    out.append(
      SubstrateRecord(
        manifest=manifest_name,
        image=record.image,
        rule_id=rule_id,
        truth=truth,
        predicted=predicted_verdict,
        raw=raw,
        error=rule_error,
      ),
    )
  return out
