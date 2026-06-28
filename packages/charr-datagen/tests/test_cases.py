"""Tests for the case recipes: labels are exact and by construction (the single-intended-issue MVP)."""

import random

import pytest
from charr.models import Verdict
from charr.rules import BUILTIN_RULES
from charr_datagen.cases import build_case, canonical_fonts, canonical_palette
from charr_datagen.cells import Cell, build_cells

_RULE_IDS = {rule.id for rule in BUILTIN_RULES}
_CELLS = build_cells()


@pytest.mark.parametrize("cell", _CELLS, ids=lambda cell: cell.label)
def test_target_rule_gets_its_intended_verdict(cell: Cell) -> None:
  case = build_case(cell, random.Random(0))
  assert case.labels[cell.rule_id] is cell.polarity


@pytest.mark.parametrize("cell", _CELLS, ids=lambda cell: cell.label)
def test_every_rule_is_labeled_in_every_case(cell: Cell) -> None:
  case = build_case(cell, random.Random(1))
  assert set(case.labels) == _RULE_IDS


@pytest.mark.parametrize("cell", _CELLS, ids=lambda cell: cell.label)
def test_at_most_one_rule_fails_per_case(cell: Cell) -> None:
  case = build_case(cell, random.Random(2))
  failing = [rule_id for rule_id, verdict in case.labels.items() if verdict is Verdict.FAIL]
  if cell.polarity is Verdict.FAIL:
    assert failing == [cell.rule_id]
  else:
    assert failing == []


@pytest.mark.parametrize("cell", _CELLS, ids=lambda cell: cell.label)
def test_build_case_is_deterministic_for_a_seed(cell: Cell) -> None:
  first = build_case(cell, random.Random(7))
  second = build_case(cell, random.Random(7))
  assert first.labels == second.labels
  assert first.scene == second.scene


def test_canonical_palette_is_nonempty_ascii() -> None:
  palette = canonical_palette()
  assert palette
  assert all(name.isascii() for name in palette)


def test_canonical_fonts_is_nonempty_ascii() -> None:
  fonts = canonical_fonts()
  assert fonts
  assert all(font.isascii() for font in fonts)
