"""Tests for the recipe registry: coverage, by-construction labels, invariance, and config-relative violations.

These are the seed-robust tests the ADRs call for (docs/adr/0018-0021). Coverage is pure inspection of the registry
metadata (no generation, no seed). Label correctness and invariance are checked per ``(cell, type)`` via ``assemble`` -
because the chart type changes the NA pattern, the label vector is a property of ``(cell, type)``, invariant to both the
seed and which concrete colours/fonts the sampled config supplies. The config-relative tests confirm the off-palette
colour and unapproved font are true fails by construction.
"""

import random

import pytest
from charr.models import Verdict
from charr_datagen.cells import Cell, build_cells
from charr_datagen.colour import T_VIOLATION, T_WITHIN, delta_e2000, srgb_hex_to_lab
from charr_datagen.configs import sample_config
from charr_datagen.fonts import SUPPORTED_FONTS, are_distinct
from charr_datagen.recipes import (
  ALL_RULES,
  GLOBAL_DEFECTS,
  REGISTRY,
  ChartType,
  assemble,
  capable_types,
)
from charr_datagen.scenes import DataLabels

_CELLS = build_cells()
_PAIRS: list[tuple[Cell, ChartType]] = [(cell, chart_type) for cell in _CELLS for chart_type in capable_types(cell)]
_PAIR_IDS = [f"{cell.label}:{chart_type.name}" for cell, chart_type in _PAIRS]
_CONFIG = sample_config("config-00", random.Random(0))
_FONT_BY_NAME = {font.name: font for font in SUPPORTED_FONTS}


def _type_named(cell: Cell, name: str) -> ChartType:
  return next(chart_type for chart_type in capable_types(cell) if chart_type.name == name)


@pytest.mark.parametrize("cell", _CELLS, ids=lambda cell: cell.label)
def test_every_cell_is_servable_by_some_chart_type(cell: Cell) -> None:
  # Pure metadata: this would fail loudly if a rule were added with no chart type able to realize its pass/fail/NA.
  assert capable_types(cell), f"cell {cell.label} is unservable by any registered chart type"


@pytest.mark.parametrize(("cell", "chart_type"), _PAIRS, ids=_PAIR_IDS)
def test_assembled_labels_are_correct_by_construction(cell: Cell, chart_type: ChartType) -> None:
  case = assemble(cell, chart_type, _CONFIG, random.Random(0))
  assert set(case.labels) == set(ALL_RULES)
  assert case.labels[cell.rule_id] is cell.polarity
  failing = [rule_id for rule_id, verdict in case.labels.items() if verdict is Verdict.FAIL]
  assert failing == ([cell.rule_id] if cell.polarity is Verdict.FAIL else [])
  for na_rule in chart_type.na_rules:
    if na_rule != cell.rule_id:
      assert case.labels[na_rule] is Verdict.NOT_APPLICABLE


@pytest.mark.parametrize(("cell", "chart_type"), _PAIRS, ids=_PAIR_IDS)
def test_labels_are_invariant_across_seeds_and_configs(cell: Cell, chart_type: ChartType) -> None:
  configs = [sample_config(f"config-{index:02d}", random.Random(index)) for index in range(3)]
  vectors = {
    tuple(
      sorted(
        (rule_id, verdict.value)
        for rule_id, verdict in assemble(cell, chart_type, config, random.Random(seed)).labels.items()
      )
    )
    for config in configs
    for seed in range(3)
  }
  assert len(vectors) == 1, "label vector must depend only on (cell, type), not on the seed or the sampled config"


def test_compliant_case_draws_colours_and_font_from_the_config() -> None:
  cell = Cell("has-title", Verdict.PASS)
  for seed in range(10):
    case = assemble(cell, _type_named(cell, "bar"), _CONFIG, random.Random(seed))
    assert all(series.color in _CONFIG.palette for series in case.scene.series)
    assert case.scene.font_family in _CONFIG.font_names()


def test_palette_violation_recolours_every_element_off_palette() -> None:
  cell = Cell("palette-compliance", Verdict.FAIL)
  palette_labs = [srgb_hex_to_lab(colour) for colour in _CONFIG.palette]
  for name in ("bar", "pie"):
    for seed in range(10):
      case = assemble(cell, _type_named(cell, name), _CONFIG, random.Random(seed))
      drawn = [series.color for series in case.scene.series] + list(case.scene.palette)
      for colour in drawn:
        lab = srgb_hex_to_lab(colour)
        assert min(delta_e2000(lab, palette) for palette in palette_labs) >= T_VIOLATION


def test_font_violation_uses_a_distinct_unapproved_font() -> None:
  cell = Cell("font-compliance", Verdict.FAIL)
  for seed in range(15):
    case = assemble(cell, _type_named(cell, "bar"), _CONFIG, random.Random(seed))
    family = case.scene.font_family
    assert family not in _CONFIG.font_names()
    assert all(are_distinct(_FONT_BY_NAME[family], approved) for approved in _CONFIG.fonts)


def test_no_overlapping_rule_is_a_symmetric_data_label_contrast() -> None:
  # The fail crowds the value labels and the pass spreads the same labels, so both polarities carry labels and only the
  # collision distinguishes them - label presence cannot leak the verdict. Unrelated cells carry no value labels.
  fail = Cell("no-overlapping-elements", Verdict.FAIL)
  passing = Cell("no-overlapping-elements", Verdict.PASS)
  for name in ("bar", "line", "scatter", "pie"):
    fail_scene = assemble(fail, _type_named(fail, name), _CONFIG, random.Random(1)).scene
    pass_scene = assemble(passing, _type_named(passing, name), _CONFIG, random.Random(1)).scene
    assert fail_scene.data_labels is DataLabels.COLLIDING
    assert pass_scene.data_labels is DataLabels.SEPARATED
  other = Cell("has-title", Verdict.PASS)
  assert assemble(other, _type_named(other, "bar"), _CONFIG, random.Random(1)).scene.data_labels is DataLabels.NONE


def test_background_contrast_fail_blends_a_series_while_pass_keeps_the_background_distinct() -> None:
  # FAIL paints the canvas the exact colour of a plotted series (it blends in); PASS paints it a colour clearly
  # separated from every series. Both sides therefore carry a (possibly tinted) background, so a tinted canvas is not
  # the cue - only whether it matches a series is. Pie is NA for this rule, so it never serves these cells.
  fail = Cell("background-series-contrast", Verdict.FAIL)
  passing = Cell("background-series-contrast", Verdict.PASS)
  for name in ("bar", "line", "scatter"):
    for seed in range(10):
      fail_scene = assemble(fail, _type_named(fail, name), _CONFIG, random.Random(seed)).scene
      assert fail_scene.background in {series.color for series in fail_scene.series}
      pass_scene = assemble(passing, _type_named(passing, name), _CONFIG, random.Random(seed)).scene
      background_lab = srgb_hex_to_lab(pass_scene.background)
      assert all(delta_e2000(background_lab, srgb_hex_to_lab(series.color)) >= T_WITHIN for series in pass_scene.series)


def test_background_contrast_fail_keeps_every_series_colour_on_the_palette() -> None:
  # The fail recolours nothing - it only matches the canvas to an existing series - so it never doubles as a
  # palette-compliance fail (single-intended-issue, docs/adr/0016).
  cell = Cell("background-series-contrast", Verdict.FAIL)
  for seed in range(10):
    scene = assemble(cell, _type_named(cell, "bar"), _CONFIG, random.Random(seed)).scene
    assert all(series.color in _CONFIG.palette for series in scene.series)


def test_non_background_cells_keep_the_white_canvas() -> None:
  other = Cell("has-title", Verdict.PASS)
  assert assemble(other, _type_named(other, "bar"), _CONFIG, random.Random(1)).scene.background == "#ffffff"


def test_global_defects_cover_every_rule() -> None:
  assert set(GLOBAL_DEFECTS) == set(ALL_RULES)


def test_registry_is_non_empty_and_named_uniquely() -> None:
  names = [chart_type.name for chart_type in REGISTRY]
  assert names
  assert len(set(names)) == len(names)
