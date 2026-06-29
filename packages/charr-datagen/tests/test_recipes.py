"""Tests for the chart-type recipe registry: coverage, by-construction labels, and seed-invariance.

These are the seed-robust tests ADR-0018 calls for. Coverage is a pure inspection of the registry metadata (no
generation, no seed). Label correctness and seed-invariance are checked per ``(cell, type)`` via ``assemble`` - because
the chart type changes the NA pattern, the label vector is a property of ``(cell, type)``, not of the cell alone, and is
invariant to the seed (which drives only label-neutral choices).
"""

import random

import pytest
from charr.models import Verdict
from charr_datagen.cells import Cell, build_cells
from charr_datagen.recipes import (
  ALL_RULES,
  GLOBAL_DEFECTS,
  REGISTRY,
  ChartType,
  assemble,
  canonical_fonts,
  canonical_palette,
  capable_types,
)

_CELLS = build_cells()
_PAIRS: list[tuple[Cell, ChartType]] = [(cell, chart_type) for cell in _CELLS for chart_type in capable_types(cell)]
_PAIR_IDS = [f"{cell.label}:{chart_type.name}" for cell, chart_type in _PAIRS]


@pytest.mark.parametrize("cell", _CELLS, ids=lambda cell: cell.label)
def test_every_cell_is_servable_by_some_chart_type(cell: Cell) -> None:
  # Pure metadata: this would fail loudly if a rule were added with no chart type able to realize its pass/fail/NA.
  assert capable_types(cell), f"cell {cell.label} is unservable by any registered chart type"


@pytest.mark.parametrize(("cell", "chart_type"), _PAIRS, ids=_PAIR_IDS)
def test_assembled_labels_are_correct_by_construction(cell: Cell, chart_type: ChartType) -> None:
  case = assemble(cell, chart_type, random.Random(0))
  assert set(case.labels) == set(ALL_RULES)
  assert case.labels[cell.rule_id] is cell.polarity
  failing = [rule_id for rule_id, verdict in case.labels.items() if verdict is Verdict.FAIL]
  assert failing == ([cell.rule_id] if cell.polarity is Verdict.FAIL else [])
  for na_rule in chart_type.na_rules:
    if na_rule != cell.rule_id:
      assert case.labels[na_rule] is Verdict.NOT_APPLICABLE


@pytest.mark.parametrize(("cell", "chart_type"), _PAIRS, ids=_PAIR_IDS)
def test_labels_are_seed_invariant_for_a_fixed_cell_and_type(cell: Cell, chart_type: ChartType) -> None:
  vectors = {
    tuple(
      sorted(
        (rule_id, verdict.value) for rule_id, verdict in assemble(cell, chart_type, random.Random(seed)).labels.items()
      )
    )
    for seed in range(5)
  }
  assert len(vectors) == 1, "label vector must not depend on the seed (the seed drives only label-neutral choices)"


def test_global_defects_cover_every_rule() -> None:
  assert set(GLOBAL_DEFECTS) == set(ALL_RULES)


def test_registry_is_non_empty_and_named_uniquely() -> None:
  names = [chart_type.name for chart_type in REGISTRY]
  assert names
  assert len(set(names)) == len(names)


def test_canonical_palette_and_fonts_are_nonempty_ascii() -> None:
  # These strings are written into the dataset's charr.toml and shown to the model, so they must be present and ASCII.
  palette = canonical_palette()
  fonts = canonical_fonts()
  assert palette
  assert all(name.isascii() for name in palette)
  assert fonts
  assert all(font.isascii() for font in fonts)
