"""Orchestration: run the enabled rules over each image and reconcile the model's answers into a report.

This module is pure coordination. It depends on the ``LlmClient`` Protocol rather than the concrete client, performs no
HTTP and no printing, and is the API-ready core a future HTTP/MCP layer would call. Reconciliation is strict: a flaky
small model that omits, duplicates, or invents a rule id fails the run loudly instead of silently passing a chart.
"""

from collections.abc import Sequence
from pathlib import Path

from charr.config import Config
from charr.llm import LlmClient
from charr.models import CharrError, ImageReport, Report, Rule, RuleId, RuleVerdict, Verdict
from charr.rules import select_enabled_rules


class CheckerError(CharrError):
  """Raised when no rules are enabled or the model's verdicts do not line up with the requested rules."""


def run_check(images: Sequence[Path], config: Config, client: LlmClient) -> Report:
  """Check every image against the enabled rules and aggregate the per-image results into a ``Report``.

  :param images: The image files to check.
  :param config: The active configuration determining which rules run.
  :param client: The LLM client used to evaluate each image.
  :return: The aggregated report across all images.
  :raises CheckerError: If no rules are enabled, or the model's verdicts do not match the requested rules.
  """
  try:
    rules = select_enabled_rules(config.rules.enable, config.rules.disable)
  except KeyError as exc:
    msg = str(exc).strip("'")
    raise CheckerError(msg) from exc
  if not rules:
    msg = "no rules are enabled; nothing to check"
    raise CheckerError(msg)
  requested = [rule.id for rule in rules]
  to_send, gated_na = _split_config_gated(rules, config)
  sent = [rule.id for rule in to_send]
  reports: list[ImageReport] = []
  for image in images:
    by_id = {verdict.rule_id: verdict for verdict in gated_na}
    if to_send:
      response = client.check_image(image=image, rules=to_send, config=config)
      by_id.update({verdict.rule_id: verdict for verdict in _reconcile(image, sent, response.results)})
    reports.append(ImageReport(image=str(image), verdicts=[by_id[rule_id] for rule_id in requested]))
  return Report(images=reports)


def _split_config_gated(rules: Sequence[Rule], config: Config) -> tuple[list[Rule], list[RuleVerdict]]:
  """Partition ``rules`` into those to send to the model and deterministic ``not_applicable`` verdicts.

  A rule whose :attr:`~charr.models.Rule.na_without` config field is empty cannot be judged - there is no palette or
  font to compare against - so it resolves to ``not_applicable`` here and is never sent. This makes the outcome a hard
  guarantee (not a request the LLM might ignore) and trims the rule from the vision call (issue #14).
  """
  to_send: list[Rule] = []
  gated_na: list[RuleVerdict] = []
  for rule in rules:
    field = rule.na_without
    if field is not None and not getattr(config, field):
      rationale = f"The {field} expectation is not configured, so this rule is not applicable."
      gated_na.append(RuleVerdict(rule_id=rule.id, verdict=Verdict.NOT_APPLICABLE, rationale=rationale))
    else:
      to_send.append(rule)
  return to_send, gated_na


def _reconcile(image: Path, requested: Sequence[RuleId], verdicts: Sequence[RuleVerdict]) -> list[RuleVerdict]:
  """Return verdicts in requested-rule order, erroring on any unknown, duplicate, or missing rule id."""
  requested_set = set(requested)
  by_id: dict[RuleId, RuleVerdict] = {}
  for verdict in verdicts:
    if verdict.rule_id not in requested_set:
      msg = f"model returned an unknown rule id {verdict.rule_id!r} for {image}"
      raise CheckerError(msg)
    if verdict.rule_id in by_id:
      msg = f"model returned a duplicate verdict for rule {verdict.rule_id!r} on {image}"
      raise CheckerError(msg)
    by_id[verdict.rule_id] = verdict
  missing = [rule_id for rule_id in requested if rule_id not in by_id]
  if missing:
    msg = f"model omitted verdict(s) for rule(s) {missing} on {image}"
    raise CheckerError(msg)
  return [by_id[rule_id] for rule_id in requested]
