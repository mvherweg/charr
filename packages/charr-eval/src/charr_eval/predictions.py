"""Loading a saved ``charr check`` output as the predictions ``charr-eval`` scores against (docs/adr/0025).

This is the read side of the run/score split: ``charr check`` produces a :class:`~charr.models.Report` (its JSON on
stdout), and the evaluator consumes that saved report instead of driving the checker itself. The report is indexed by
image so the scorer can join each ground-truth label to the checker's verdict for the same image.

The join key is the image's resolved absolute path. :func:`prediction_image_key` is the one place that decides image
identity - the check-output-side mirror of :func:`charr_eval.manifest.resolve_image` - so a future switch to a
declared image id (issue #31) is a change here alone.
"""

from pathlib import Path

from charr.models import CharrError, Report, RuleId, Verdict
from pydantic import ValidationError

# One image's predictions: rule id -> (verdict, the model's raw rationale), the same shape the runner folds into
# substrate records. Keyed by resolved absolute image path in :func:`load_predictions`.
type PredictionsByImage = dict[Path, dict[RuleId, tuple[Verdict, str]]]


def load_predictions(path: Path) -> PredictionsByImage:
  """Load a saved ``charr check`` JSON report and index its verdicts by resolved image path.

  :param path: The saved check output to read.
  :return: A mapping from each image's resolved absolute path to its ``rule_id -> (verdict, rationale)`` verdicts.
  :raises CharrError: If the file is not a valid report, or names the same image twice (both mean the predictions
    cannot be trusted - a dataset/input error, distinct from a programming fault, so the CLI reports it cleanly).
  """
  try:
    report = Report.from_json(path.read_text(encoding="utf-8"))
  except ValidationError as exc:
    msg = f"{path}: invalid charr check output: {exc}"
    raise CharrError(msg) from exc
  predictions: PredictionsByImage = {}
  for image_report in report.images:
    key = prediction_image_key(image_report.image)
    if key in predictions:
      msg = f"{path}: duplicate prediction for image {key}"
      raise CharrError(msg)
    predictions[key] = {verdict.rule_id: (verdict.verdict, verdict.rationale) for verdict in image_report.verdicts}
  return predictions


def prediction_image_key(image: str) -> Path:
  """Return the join key for a prediction's image: its resolved absolute path.

  This mirrors :func:`charr_eval.manifest.resolve_image` on the check-output side so the two agree, and is the single
  swappable seam for image identity (a declared id may replace it later; issue #31). ``charr check`` already writes
  absolute paths, so this is usually a no-op; a relative path resolves against the current directory.

  :param image: The image path string as recorded in the check output.
  :return: The resolved absolute path.
  """
  return Path(image).resolve()
