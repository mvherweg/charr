"""Drive the checker over a manifest's images and capture each per-rule outcome as a substrate record.

This is where ``charr-eval`` actually *uses* the checker (docs/adr/0010): it calls :func:`charr.checker.run_check` one
image at a time so a single bad image degrades to an ``error`` bucket instead of aborting the whole evaluation. The
checker's config is discovered next to the manifest, so a generated dataset's own ``charr.toml`` (palette/font
expectations) is what the checker is told. The captured raw rationale is kept on each record for failure analysis.
"""

from pathlib import Path

from charr.checker import run_check
from charr.config import Config
from charr.llm import LlmClient
from charr.models import CharrError, RuleId, Verdict

from charr_eval.manifest import ManifestRecord, read_manifest, resolve_image
from charr_eval.scoring import SubstrateRecord


def evaluate_manifest(manifest_path: Path, *, client: LlmClient, config: Config) -> list[SubstrateRecord]:
  """Run the checker over every image in ``manifest_path`` and return the per-rule substrate records.

  :param manifest_path: The manifest to evaluate; its filename stem names the manifest in the results.
  :param client: The LLM client the checker drives (a real backend in the CLI; a fake in tests).
  :param config: The checker configuration to evaluate under (typically discovered next to the manifest).
  :return: One :class:`SubstrateRecord` per ``(image, rule)`` in the manifest.
  :raises ValueError: If the manifest itself is malformed (a dataset error, not a checker error).
  """
  manifest_name = manifest_path.stem
  records: list[SubstrateRecord] = []
  for record in read_manifest(manifest_path):
    predicted, error = _check_one(resolve_image(manifest_path, record), config=config, client=client)
    records.extend(_image_records(manifest_name, record, predicted, error))
  return records


def _check_one(
  image: Path,
  *,
  config: Config,
  client: LlmClient,
) -> tuple[dict[RuleId, tuple[Verdict, str]], str | None]:
  """Check one image, returning ``(rule_id -> (verdict, rationale), error)``; ``error`` set means the image errored."""
  if not image.is_file():
    return {}, f"image not found: {image}"
  try:
    report = run_check([image], config, client)
  except CharrError as exc:
    return {}, str(exc)
  verdicts = {verdict.rule_id: (verdict.verdict, verdict.rationale) for verdict in report.images[0].verdicts}
  return verdicts, None


def _image_records(
  manifest_name: str,
  record: ManifestRecord,
  predicted: dict[RuleId, tuple[Verdict, str]],
  error: str | None,
) -> list[SubstrateRecord]:
  """Fold one image's outcome into per-rule substrate records, mapping a checker error to the error bucket."""
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
