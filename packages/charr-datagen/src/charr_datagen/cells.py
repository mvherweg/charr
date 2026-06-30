"""The stratification cells and the apportionment allocator that turns ``--samples N`` into per-cell counts.

A generation run stratifies on ``(rule, polarity)`` only (about twenty cells); library and chart parameters are
randomized within a cell, not stratified (see docs/adr/0014). This module is pure: it defines the cell catalog, the
priority order used both for apportionment and for under-budget coverage, and the deterministic allocation of a sample
budget across the cells. It performs no rendering and no I/O so it is trivially testable offline.
"""

from dataclasses import dataclass

from charr.models import RuleId, Verdict
from charr.rules import BUILTIN_RULES

# Allowed target verdicts per rule, in priority order within the rule (fail before pass before not_applicable).
# ``not_applicable`` is listed only for rules that are genuinely conditional: a rule that always applies (every chart
# can carry a title) has no NA cell. Keep this aligned with the rule prompts in charr.rules; adding an NA here without a
# recipe that makes the chart trigger it would create an uncoverable cell.
_POLARITIES_BY_RULE: dict[RuleId, tuple[Verdict, ...]] = {
  "has-title": (Verdict.FAIL, Verdict.PASS),
  "axes-labeled": (Verdict.FAIL, Verdict.PASS, Verdict.NOT_APPLICABLE),
  "no-overlapping-elements": (Verdict.FAIL, Verdict.PASS),
  "palette-compliance": (Verdict.FAIL, Verdict.PASS),
  "font-compliance": (Verdict.FAIL, Verdict.PASS),
  "axis-units": (Verdict.FAIL, Verdict.PASS, Verdict.NOT_APPLICABLE),
  "legend-when-multiple-groups": (Verdict.FAIL, Verdict.PASS, Verdict.NOT_APPLICABLE),
  "zero-baseline": (Verdict.FAIL, Verdict.PASS, Verdict.NOT_APPLICABLE),
  "background-series-contrast": (Verdict.FAIL, Verdict.PASS),
  "gridline-series-contrast": (Verdict.FAIL, Verdict.PASS, Verdict.NOT_APPLICABLE),
  "gridline-weight": (Verdict.FAIL, Verdict.PASS, Verdict.NOT_APPLICABLE),
}


@dataclass(frozen=True)
class Cell:
  """One stratification cell: a target verdict for a single rule.

  A generated case in this cell renders a chart for which ``rule_id`` evaluates to ``polarity`` by construction, while
  every other rule is held to ``pass`` or ``not_applicable`` (the single-intended-issue MVP of docs/adr/0016).
  """

  rule_id: RuleId
  polarity: Verdict

  @property
  def label(self) -> str:
    """Short, filesystem- and log-friendly identifier, e.g. ``has-title-fail``.

    :return: The rule id joined to the polarity value by a hyphen.
    """
    return f"{self.rule_id}-{self.polarity.value}"


@dataclass(frozen=True)
class Allocation:
  """The result of apportioning a sample budget across the priority-ordered cells."""

  cells: tuple[Cell, ...]
  counts: tuple[int, ...]

  @property
  def total(self) -> int:
    """Return the number of cases allocated (equals the requested ``samples``).

    :return: Sum of the per-cell counts.
    """
    return sum(self.counts)

  @property
  def uncovered(self) -> tuple[Cell, ...]:
    """Return the cells that received no budget (only possible when ``samples`` is below the cell count).

    :return: The cells whose allocated count is zero, in priority order.
    """
    return tuple(cell for cell, count in zip(self.cells, self.counts, strict=True) if count == 0)

  @property
  def min_for_full_coverage(self) -> int:
    """Return the smallest ``samples`` that gives every cell at least one case.

    :return: The total number of cells.
    """
    return len(self.cells)


def build_cells() -> tuple[Cell, ...]:
  """Build the priority-ordered cell catalog.

  Priority order (docs/adr/0014): every rule's ``fail`` then ``pass`` first, in catalog (rule-id) order, then every
  conditional rule's ``not_applicable`` in catalog order. Under-budget runs cover the highest-priority cells this order
  yields, so violation- and pass-detection are sampled before the rarer NA cells.

  :return: The cells, highest priority first.
  """
  rule_ids = [rule.id for rule in BUILTIN_RULES]
  _check_catalog(rule_ids)
  primary = [
    Cell(rule_id, polarity)
    for rule_id in rule_ids
    for polarity in _POLARITIES_BY_RULE[rule_id]
    if polarity is not Verdict.NOT_APPLICABLE
  ]
  not_applicable = [
    Cell(rule_id, Verdict.NOT_APPLICABLE)
    for rule_id in rule_ids
    if Verdict.NOT_APPLICABLE in _POLARITIES_BY_RULE[rule_id]
  ]
  return tuple(primary + not_applicable)


def allocate(samples: int, cells: tuple[Cell, ...]) -> Allocation:
  """Apportion ``samples`` cases across ``cells`` deterministically.

  Each cell receives ``floor(samples / len(cells))``; the remainder is handed out one per cell down the priority order.
  The mapping is a pure function of ``samples`` and the cell order, so a run is reproducible.

  :param samples: Total number of cases to generate; must be non-negative.
  :param cells: The priority-ordered cells to allocate across; must be non-empty.
  :return: The allocation, parallel to ``cells``.
  :raises ValueError: If ``samples`` is negative or ``cells`` is empty.
  """
  if samples < 0:
    msg = f"samples must be non-negative, got {samples}"
    raise ValueError(msg)
  if not cells:
    msg = "cannot allocate across an empty cell catalog"
    raise ValueError(msg)
  base, remainder = divmod(samples, len(cells))
  counts = tuple(base + (1 if index < remainder else 0) for index in range(len(cells)))
  return Allocation(cells=cells, counts=counts)


def _check_catalog(rule_ids: list[RuleId]) -> None:
  """Fail loudly if the polarity map and the built-in rule catalog have drifted apart."""
  catalog = set(rule_ids)
  declared = set(_POLARITIES_BY_RULE)
  if catalog != declared:
    missing = sorted(catalog - declared)
    extra = sorted(declared - catalog)
    msg = f"polarity map is out of sync with BUILTIN_RULES (missing {missing}, unexpected {extra})"
    raise ValueError(msg)
