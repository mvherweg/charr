"""Tests for the stratification cells and the apportionment allocator."""

import pytest
from charr.models import Verdict
from charr.rules import BUILTIN_RULES
from charr_datagen.cells import Cell, allocate, build_cells


def test_build_cells_covers_every_rule_with_fail_and_pass() -> None:
  cells = build_cells()
  for rule in BUILTIN_RULES:
    polarities = {cell.polarity for cell in cells if cell.rule_id == rule.id}
    assert Verdict.FAIL in polarities
    assert Verdict.PASS in polarities


def test_build_cells_yields_one_cell_per_rule_polarity() -> None:
  # Eight rules carry fail+pass, four of those add a not_applicable cell, and background-series-contrast adds fail+pass:
  # 9 rules with fail+pass (18) + 4 NA cells = 22. Bump this when a rule or polarity is added (a deliberate tripwire).
  assert len(build_cells()) == 22


def test_priority_order_puts_all_fail_and_pass_before_any_not_applicable() -> None:
  cells = build_cells()
  last_primary = max(i for i, cell in enumerate(cells) if cell.polarity is not Verdict.NOT_APPLICABLE)
  first_na = min(i for i, cell in enumerate(cells) if cell.polarity is Verdict.NOT_APPLICABLE)
  assert last_primary < first_na


def test_fail_precedes_pass_within_each_rule() -> None:
  cells = build_cells()
  for rule in BUILTIN_RULES:
    indices = {cell.polarity: i for i, cell in enumerate(cells) if cell.rule_id == rule.id}
    assert indices[Verdict.FAIL] < indices[Verdict.PASS]


def test_allocate_distributes_evenly_when_divisible() -> None:
  cells = build_cells()
  allocation = allocate(2 * len(cells), cells)
  assert set(allocation.counts) == {2}
  assert allocation.total == 2 * len(cells)


def test_allocate_hands_the_remainder_to_the_highest_priority_cells() -> None:
  cells = build_cells()
  allocation = allocate(len(cells) + 3, cells)
  assert allocation.counts[:3] == (2, 2, 2)
  assert allocation.counts[3] == 1


def test_allocate_under_budget_leaves_the_lowest_priority_cells_uncovered() -> None:
  cells = build_cells()
  allocation = allocate(3, cells)
  assert allocation.total == 3
  assert allocation.uncovered == cells[3:]
  assert allocation.min_for_full_coverage == len(cells)


def test_allocate_rejects_negative_samples() -> None:
  with pytest.raises(ValueError, match="non-negative"):
    allocate(-1, build_cells())


def test_allocate_rejects_an_empty_catalog() -> None:
  with pytest.raises(ValueError, match="empty"):
    allocate(5, ())


def test_cell_label_joins_rule_and_polarity() -> None:
  assert Cell("has-title", Verdict.FAIL).label == "has-title-fail"
