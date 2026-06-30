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
  _drawn_colours,
  assemble,
  capable_types,
)
from charr_datagen.scenes import ChartScene, DataLabels

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


def _min_distance_to_marks(colour: str, scene: ChartScene) -> float:
  # Smallest deltaE2000 from ``colour`` (a background or gridline) to any colour the chart plots. Delegates to
  # recipes._drawn_colours so the test cannot drift from how the generator defines "colours used in the graph".
  colour_lab = srgb_hex_to_lab(colour)
  return min(delta_e2000(colour_lab, srgb_hex_to_lab(mark)) for mark in _drawn_colours(scene))


def test_background_contrast_fail_blends_a_mark_while_pass_keeps_the_background_clear() -> None:
  # FAIL paints the canvas within T_WITHIN of a plotted mark (not reliably distinguishable -> it blends); PASS paints it
  # at least T_VIOLATION from every mark (clearly distinct). The (T_WITHIN, T_VIOLATION) middle is never generated, so
  # labels stay unambiguous. Judged purely on background-vs-mark distance, irrespective of the palette. Pie has a
  # background too, so it serves this rule (a slice blends into the canvas).
  fail = Cell("background-series-contrast", Verdict.FAIL)
  passing = Cell("background-series-contrast", Verdict.PASS)
  for name in ("bar", "line", "scatter", "pie"):
    for seed in range(10):
      fail_scene = assemble(fail, _type_named(fail, name), _CONFIG, random.Random(seed)).scene
      assert _min_distance_to_marks(fail_scene.background, fail_scene) <= T_WITHIN
      pass_scene = assemble(passing, _type_named(passing, name), _CONFIG, random.Random(seed)).scene
      assert _min_distance_to_marks(pass_scene.background, pass_scene) >= T_VIOLATION


def test_background_contrast_leaves_the_plotted_mark_colours_untouched() -> None:
  # The rule only repaints the canvas; the marks keep their config colours, so it never doubles as a palette-compliance
  # fail (single-intended-issue, docs/adr/0016). The background itself is deliberately palette-independent.
  cell = Cell("background-series-contrast", Verdict.FAIL)
  for seed in range(10):
    scene = assemble(cell, _type_named(cell, "bar"), _CONFIG, random.Random(seed)).scene
    assert all(series.color in _CONFIG.palette for series in scene.series)


def test_non_background_cells_keep_the_white_canvas() -> None:
  other = Cell("has-title", Verdict.PASS)
  assert assemble(other, _type_named(other, "bar"), _CONFIG, random.Random(1)).scene.background == "#ffffff"


def test_gridline_contrast_blends_a_series_on_fail_and_stays_clear_and_visible_on_pass() -> None:
  # FAIL colours the grid within T_WITHIN of a series (reads as data); PASS keeps it at least T_VIOLATION from every
  # series. Both force the grid on so the rule is judgeable, and both carry a coloured grid - so a coloured grid is not
  # the cue, only whether it lands near a series is. Pie has no cartesian grid, so it is NA and never serves fail/pass.
  fail = Cell("gridline-series-contrast", Verdict.FAIL)
  passing = Cell("gridline-series-contrast", Verdict.PASS)
  for name in ("bar", "line", "scatter"):
    for seed in range(10):
      fail_scene = assemble(fail, _type_named(fail, name), _CONFIG, random.Random(seed)).scene
      assert fail_scene.grid is True
      assert _min_distance_to_marks(fail_scene.gridline_color, fail_scene) <= T_WITHIN
      pass_scene = assemble(passing, _type_named(passing, name), _CONFIG, random.Random(seed)).scene
      assert pass_scene.grid is True
      assert _min_distance_to_marks(pass_scene.gridline_color, pass_scene) >= T_VIOLATION


def test_gridline_contrast_is_not_applicable_for_pie() -> None:
  # A pie has no cartesian grid, so the rule is NA for it - the NA cell is served only by pie (like zero-baseline).
  na = Cell("gridline-series-contrast", Verdict.NOT_APPLICABLE)
  assert [chart_type.name for chart_type in capable_types(na)] == ["pie"]
  assert assemble(na, _type_named(na, "pie"), _CONFIG, random.Random(1)).labels[na.rule_id] is Verdict.NOT_APPLICABLE


def test_non_gridline_cells_keep_the_neutral_grey_grid() -> None:
  other = Cell("has-title", Verdict.PASS)
  assert assemble(other, _type_named(other, "bar"), _CONFIG, random.Random(1)).scene.gridline_color == "#b0b0b0"


def test_gridline_weight_fail_makes_the_grid_compete_while_pass_keeps_it_thin() -> None:
  # FAIL strokes the grid at least as heavily as the data lines (ratio >= 1.0, so it competes with the data); PASS keeps
  # it clearly thinner (ratio <= 0.5). The (0.5, 1.0) middle is never generated, so labels stay unambiguous. Both force
  # the grid on, so a visible grid is not the cue - only its weight relative to the lines is.
  fail = Cell("gridline-weight", Verdict.FAIL)
  passing = Cell("gridline-weight", Verdict.PASS)
  for seed in range(10):
    fail_scene = assemble(fail, _type_named(fail, "line"), _CONFIG, random.Random(seed)).scene
    assert fail_scene.grid is True
    assert fail_scene.gridline_width / fail_scene.series_width >= 1.0
    pass_scene = assemble(passing, _type_named(passing, "line"), _CONFIG, random.Random(seed)).scene
    assert pass_scene.grid is True
    assert pass_scene.gridline_width / pass_scene.series_width <= 0.5


def test_gridline_weight_is_not_applicable_off_line_charts() -> None:
  # The rule compares the grid stroke to the series *line* weight, so only the line type can serve its pass/fail; bar,
  # scatter, and pie have no line to compare against and serve only its NA cell.
  fail = Cell("gridline-weight", Verdict.FAIL)
  assert [chart_type.name for chart_type in capable_types(fail)] == ["line"]
  na = Cell("gridline-weight", Verdict.NOT_APPLICABLE)
  assert {chart_type.name for chart_type in capable_types(na)} == {"bar", "scatter", "pie"}
  for name in ("bar", "scatter", "pie"):
    case = assemble(na, _type_named(na, name), _CONFIG, random.Random(1))
    assert case.labels[na.rule_id] is Verdict.NOT_APPLICABLE


def test_non_gridline_weight_cells_keep_the_default_stroke_widths() -> None:
  other = Cell("has-title", Verdict.PASS)
  scene = assemble(other, _type_named(other, "line"), _CONFIG, random.Random(1)).scene
  assert (scene.series_width, scene.gridline_width) == (2.0, 0.8)


def test_global_defects_cover_every_rule() -> None:
  assert set(GLOBAL_DEFECTS) == set(ALL_RULES)


def test_registry_is_non_empty_and_named_uniquely() -> None:
  names = [chart_type.name for chart_type in REGISTRY]
  assert names
  assert len(set(names)) == len(names)
