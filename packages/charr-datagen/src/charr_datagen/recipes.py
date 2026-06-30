"""The chart-type recipe registry: compose a cell, a chart type, a domain, a style-config, and jitter into a case.

This is the heart of the generator (docs/adr/0018). A chart type is **data**: a compliant-baseline builder, the set of
rules that are structurally ``not_applicable`` for it (``na_rules``), whether it can be drawn single-group (which makes
the legend NA), and a table of type-specific defect overrides (empty for the current four types - every defect for the
built-in rules turns out to operate on shared scene fields, so the shared :data:`GLOBAL_DEFECTS` table covers them all).

Labels stay correct by construction. A chart's verdict vector is a function of its ``(cell, type)`` and the single
defect injected; the style-config (docs/adr/0019) supplies the palette and approved fonts but never changes a verdict,
because the recipe draws compliant charts *from* the config and draws each violation *outside* it: compliant colours
come from the config palette and a compliant font from its approved set, while the palette / font violations sample a
colour beyond :data:`~charr_datagen.colour.T_VIOLATION` of the palette (docs/adr/0020) and a font differing by a
distinguishing property from every approved font (docs/adr/0021). So the label is exact for any sampled config, and for
a fixed ``(cell, type, config)`` it does not depend on the seed.

To add a chart type, append a :class:`ChartType` with its baseline, ``na_rules``, and (rarely) a type-specific defect.
To add subject variety, append a :class:`~charr_datagen.domains.Domain`. The generic tests in ``tests/`` then validate
coverage and label correctness automatically; see development.md.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass, field

from charr.models import RuleId, Verdict
from charr.rules import BUILTIN_RULES

from charr_datagen.cells import Cell
from charr_datagen.colour import sample_far_from, sample_near, sample_off_palette
from charr_datagen.configs import StyleConfig
from charr_datagen.domains import DOMAINS, Domain
from charr_datagen.fonts import sample_violation
from charr_datagen.scenes import ChartKind, ChartScene, DataLabels, Series

ALL_RULES: tuple[RuleId, ...] = tuple(rule.id for rule in BUILTIN_RULES)

_LEGEND = "legend-when-multiple-groups"
_OVERLAP = "no-overlapping-elements"
_BACKGROUND = "background-series-contrast"
_GRIDLINE = "gridline-series-contrast"
_GRIDWEIGHT = "gridline-weight"

# gridline-weight is constructed as a ratio of gridline stroke width to series line width. FAIL paints the grid at least
# as heavy as the lines (ratio >= _HEAVY_RATIO_MIN, so it competes with the data); the PASS exemplar keeps it clearly
# thinner (ratio <= _LIGHT_RATIO_MAX). The (_LIGHT_RATIO_MAX, _HEAVY_RATIO_MIN) middle is never generated, so labels
# stay unambiguous. The scene's default widths sit below _LIGHT_RATIO_MAX, so the norm grid is a clean pass.
_HEAVY_RATIO_MIN = 1.0
_LIGHT_RATIO_MAX = 0.5

_TIME_LABELS: tuple[str, ...] = ("Month", "Quarter", "Week", "Year", "Period")
_SAMPLE_LABELS: tuple[str, ...] = ("Sample", "Observation", "Trial", "Specimen", "Measurement")
_MARKERS: tuple[str, ...] = ("o", "s", "^", "D", "v")

# An injector turns one rule's verdict to FAIL by mutating the scene; it may consult the active style-config (for the
# palette / approved fonts) and the rng (to sample a concrete violation). Most injectors need neither.
type Injector = Callable[[ChartScene, StyleConfig, random.Random], None]
# A baseline builds a fully-compliant scene for a chart type from a domain and the active style-config.
type Baseline = Callable[..., ChartScene]


@dataclass
class Case:
  """A generated case: the scene to render and the ground-truth verdict for every rule."""

  scene: ChartScene
  labels: dict[RuleId, Verdict]


@dataclass(frozen=True)
class ChartType:
  """A chart-type recipe, as data.

  :param name: Stable identifier (used in filenames/metadata).
  :param kind: The visual kind the backends draw.
  :param baseline: Builds a fully compliant scene of this type from ``(domain, config, rng, multi=...)``.
  :param na_rules: Rules structurally ``not_applicable`` for this type (e.g. a pie has no axes).
  :param supports_single_group: Whether the type can be drawn with one group, which makes the legend NA.
  :param extra_defects: Type-specific defect injectors, overriding :data:`GLOBAL_DEFECTS` (empty for the built-in four).
  """

  name: str
  kind: ChartKind
  baseline: Baseline
  na_rules: frozenset[RuleId]
  supports_single_group: bool
  extra_defects: dict[RuleId, Injector] = field(default_factory=dict)

  def defect_for(self, rule_id: RuleId) -> Injector:
    """Return the injector that makes ``rule_id`` fail for this type (type-specific override, else global)."""
    return self.extra_defects.get(rule_id, GLOBAL_DEFECTS[rule_id])


def build_case(cell: Cell, config: StyleConfig, rng: random.Random) -> Case:
  """Build the scene and ground-truth labels for one case in ``cell``, drawn against ``config``.

  The cell fixes the target rule and its verdict; the chart type (among those that can serve the cell), the domain, the
  numbers, and the cosmetic style are drawn from ``rng``. All of those are label-neutral, so the labels are exact.

  :param cell: The target ``(rule, polarity)`` to construct a chart for.
  :param config: The active style-config (palette + approved fonts) the chart is drawn against.
  :param rng: A seeded RNG owned by this case; drives all within-cell randomization.
  :return: The case, with labels known by construction.
  :raises ValueError: If no registered chart type can serve the cell (a registry/catalog drift the tests guard against).
  """
  capable = capable_types(cell)
  if not capable:
    msg = f"no chart type can serve cell {cell.label!r}"
    raise ValueError(msg)
  return assemble(cell, rng.choice(capable), config, rng)


def assemble(cell: Cell, chart_type: ChartType, config: StyleConfig, rng: random.Random) -> Case:
  """Build a case for ``cell`` using a specific ``chart_type`` and ``config`` (the pinned core of :func:`build_case`).

  Exposed so tests can fix the chart type and assert the labels are correct and seed-invariant for that
  ``(cell, type, config)``. The label vector depends only on ``(cell, type)`` - never on ``rng`` or which concrete
  colours/fonts the config supplies, which drive only label-neutral choices.

  :param cell: The target ``(rule, polarity)``.
  :param chart_type: The chart type to render with; must be able to serve ``cell``.
  :param config: The active style-config the chart is drawn against.
  :param rng: Seeded RNG for the label-neutral choices.
  :return: The case, with labels known by construction.
  """
  domain = rng.choice(DOMAINS)
  multi = _multi_for(cell)
  scene = chart_type.baseline(domain, config, rng, multi=multi)
  scene.font_family = rng.choice(config.fonts).name
  _jitter(scene, rng)
  labels = _baseline_labels(chart_type, multi=multi)
  if cell.polarity is Verdict.FAIL:
    chart_type.defect_for(cell.rule_id)(scene, config, rng)
    labels.update(_FAIL_COLLATERAL.get(cell.rule_id, {}))
  elif cell.polarity is Verdict.PASS and (exemplar := COMPLIANT_EXEMPLARS.get(cell.rule_id)) is not None:
    exemplar(scene, config, rng)  # show the compliant positive feature so the FAIL is a contrast, not a presence cue
  labels[cell.rule_id] = cell.polarity
  return Case(scene=scene, labels=labels)


def capable_types(cell: Cell) -> list[ChartType]:
  """Return the registered chart types that can realize ``cell`` (pure metadata; no generation, no seed).

  :param cell: The target ``(rule, polarity)``.
  :return: The chart types able to serve it, in registry order.
  """
  return [chart_type for chart_type in REGISTRY if _can_serve(chart_type, cell)]


def _can_serve(chart_type: ChartType, cell: Cell) -> bool:
  rule_id, polarity = cell.rule_id, cell.polarity
  if polarity is Verdict.NOT_APPLICABLE:
    if rule_id == _LEGEND:
      return chart_type.supports_single_group  # legend is NA only for a single-group chart
    return rule_id in chart_type.na_rules
  if rule_id == _LEGEND:
    return True  # any type can show a multi-group legend (pass) or have it removed (fail)
  return rule_id not in chart_type.na_rules


def _multi_for(cell: Cell) -> bool:
  # Single-vs-multi group is label-bearing (it sets the legend verdict), so it must be controlled, not seed-rolled.
  # Only the legend cells need a single group; every other cell is multi-group, keeping the legend a clean pass.
  if cell.rule_id == _LEGEND:
    return cell.polarity is not Verdict.NOT_APPLICABLE
  return True


def _baseline_labels(chart_type: ChartType, *, multi: bool) -> dict[RuleId, Verdict]:
  labels = dict.fromkeys(ALL_RULES, Verdict.PASS)
  for rule_id in chart_type.na_rules:
    labels[rule_id] = Verdict.NOT_APPLICABLE
  labels[_LEGEND] = Verdict.PASS if multi else Verdict.NOT_APPLICABLE
  return labels


def _jitter(scene: ChartScene, rng: random.Random) -> None:
  """Apply label-neutral cosmetic variety (never touches a verdict)."""
  scene.grid = rng.choice([True, False])
  scene.marker = rng.choice(_MARKERS)


# Dropping a numeric axis's title (the axes-labeled fail) also removes its units, so axis-units becomes NA, not a second
# failure. Keeps the single-intended-issue guarantee.
_FAIL_COLLATERAL: dict[RuleId, dict[RuleId, Verdict]] = {
  "axes-labeled": {"axis-units": Verdict.NOT_APPLICABLE},
}


# --- defect injectors (global; each introduces exactly one violation on shared scene fields) ---


def _drop_title(scene: ChartScene, _config: StyleConfig, _rng: random.Random) -> None:
  scene.title = None


def _drop_axis_labels(scene: ChartScene, _config: StyleConfig, _rng: random.Random) -> None:
  scene.x_label = None
  scene.y_label = None


def _induce_overlap(scene: ChartScene, _config: StyleConfig, _rng: random.Random) -> None:
  # Crowd the chart's real value labels so they collide. Reading a label ("38.1") reveals nothing about the verdict;
  # only seeing the collision does. The compliant exemplar (_separate_labels) draws the same labels cleanly, so label
  # presence never leaks the verdict either - the contrast is purely the overlap.
  scene.data_labels = DataLabels.COLLIDING


def _off_palette(scene: ChartScene, config: StyleConfig, rng: random.Random) -> None:
  # Recolour every drawn element with a colour clearly outside the config palette, so palette-compliance is a true fail
  # by construction (each is >= T_VIOLATION from every palette colour, docs/adr/0020).
  for series in scene.series:
    series.color = sample_off_palette(rng, config.palette)
  if scene.palette:
    scene.palette = [sample_off_palette(rng, config.palette) for _ in scene.palette]


def _unapproved_font(scene: ChartScene, config: StyleConfig, rng: random.Random) -> None:
  # A font differing by a distinguishing property from every approved font, so font-compliance is a true fail.
  scene.font_family = sample_violation(rng, config.fonts).name


def _drop_units(scene: ChartScene, _config: StyleConfig, _rng: random.Random) -> None:
  if scene.y_label and " (" in scene.y_label:
    scene.y_label = scene.y_label.split(" (")[0]


def _remove_legend(scene: ChartScene, _config: StyleConfig, _rng: random.Random) -> None:
  scene.show_legend = False


def _nonzero_baseline(scene: ChartScene, _config: StyleConfig, _rng: random.Random) -> None:
  scene.y_baseline_zero = False


def _low_background_contrast(scene: ChartScene, _config: StyleConfig, rng: random.Random) -> None:
  # Paint the canvas a colour within T_WITHIN (deltaE2000) of one plotted mark, so that mark is not reliably
  # distinguishable from the background and blends in. The rule judges background-vs-marks irrespective of the palette,
  # so the background may be any colour (off-palette is fine, exactly as the white/grey/black chrome already is). The
  # compliant exemplar (_distinct_background) keeps the canvas far from every mark, so a tinted canvas is not the cue -
  # only whether it lands near a mark is.
  scene.background = sample_near(rng, rng.choice(_drawn_colours(scene)))


def _low_gridline_contrast(scene: ChartScene, _config: StyleConfig, rng: random.Random) -> None:
  # Show the grid and colour it within T_WITHIN (deltaE2000) of one plotted series, so the gridlines are not reliably
  # distinguishable from that series and read as data. Like the background, this is judged irrespective of the palette.
  # The compliant exemplar (_distinct_gridlines) keeps the grid far from every series, so a coloured grid is not the cue
  # - only whether it lands near a series is.
  scene.grid = True
  scene.gridline_color = sample_near(rng, rng.choice(_drawn_colours(scene)))


def _heavy_gridlines(scene: ChartScene, _config: StyleConfig, rng: random.Random) -> None:
  # Show the grid and stroke it at least as heavily as the data lines (gridline >= series width), so the gridlines
  # compete with the data. Only injected on line charts (the rule is NA elsewhere). The grid keeps its neutral colour,
  # so this is purely a weight defect. The compliant exemplar (_light_gridlines) shows a thin grid, so a visible grid is
  # not the cue - only its weight relative to the lines is.
  scene.grid = True
  scene.gridline_width = scene.series_width * rng.uniform(_HEAVY_RATIO_MIN, 1.5)


# --- compliant exemplars: positive features a rule's PASS side must *show* so its FAIL is a layout contrast, not a
# presence cue. Only no-overlapping needs one: its FAIL crowds the value labels (above), so its PASS must draw the same
# labels cleanly separated. Every other rule's baseline is already a clean pass, so the table holds just this entry.


def _separate_labels(scene: ChartScene, _config: StyleConfig, _rng: random.Random) -> None:
  scene.data_labels = DataLabels.SEPARATED


def _distinct_background(scene: ChartScene, _config: StyleConfig, rng: random.Random) -> None:
  # Paint the canvas a colour at least T_VIOLATION (deltaE2000) from every plotted mark, so nothing blends - a clean,
  # unambiguous pass. Both polarities carry a sampled (non-white) background, so a tinted canvas is not the cue; only
  # whether it lands near a mark is.
  scene.background = sample_far_from(rng, _drawn_colours(scene))


def _distinct_gridlines(scene: ChartScene, _config: StyleConfig, rng: random.Random) -> None:
  # Show the grid in a colour at least T_VIOLATION (deltaE2000) from every plotted series, so it stays clearly
  # subordinate to the data. Both polarities force the grid on and carry a coloured grid, so a coloured grid is not the
  # cue; only whether it lands near a series is.
  scene.grid = True
  scene.gridline_color = sample_far_from(rng, _drawn_colours(scene))


def _light_gridlines(scene: ChartScene, _config: StyleConfig, rng: random.Random) -> None:
  # Show the grid stroked clearly thinner than the data lines (gridline <= half the series width), so it recedes behind
  # the data - a clean pass. Both polarities force the grid on, so a visible grid is not the cue; only its weight is.
  scene.grid = True
  scene.gridline_width = scene.series_width * rng.uniform(0.2, _LIGHT_RATIO_MAX)


def _drawn_colours(scene: ChartScene) -> list[str]:
  # Every data colour the chart actually plots: the series colours plus, for a pie, its per-slice palette.
  return [series.color for series in scene.series] + list(scene.palette)


COMPLIANT_EXEMPLARS: dict[RuleId, Injector] = {
  _OVERLAP: _separate_labels,
  _BACKGROUND: _distinct_background,
  _GRIDLINE: _distinct_gridlines,
  _GRIDWEIGHT: _light_gridlines,
}


GLOBAL_DEFECTS: dict[RuleId, Injector] = {
  "has-title": _drop_title,
  "axes-labeled": _drop_axis_labels,
  "no-overlapping-elements": _induce_overlap,
  "palette-compliance": _off_palette,
  "font-compliance": _unapproved_font,
  "axis-units": _drop_units,
  _LEGEND: _remove_legend,
  "zero-baseline": _nonzero_baseline,
  _BACKGROUND: _low_background_contrast,
  _GRIDLINE: _low_gridline_contrast,
  _GRIDWEIGHT: _heavy_gridlines,
}


# --- compliant baselines (one per kind; each returns a fully-passing scene of that kind, coloured from the config) ---


def _bar_baseline(domain: Domain, config: StyleConfig, rng: random.Random, *, multi: bool) -> ChartScene:
  names = _series_names(domain, rng, multi=multi, palette_size=config.palette_size)
  count = rng.randint(3, min(5, len(domain.categories)))
  categories = list(rng.sample(domain.categories, count))
  series = [
    Series(name=name, x=list(categories), y=_values(domain, rng, count), color=color)
    for name, color in zip(names, _colours(config, rng, len(names)), strict=True)
  ]
  return ChartScene(
    kind=ChartKind.BAR,
    title=rng.choice(domain.titles),
    x_label=domain.category_axis_label,
    y_label=_y_label(domain),
    series=series,
    show_legend=multi,
  )


def _line_baseline(domain: Domain, config: StyleConfig, rng: random.Random, *, multi: bool) -> ChartScene:
  names = _series_names(domain, rng, multi=multi, palette_size=config.palette_size)
  count = rng.randint(5, 8)
  xs = [float(step) for step in range(1, count + 1)]
  series = [
    Series(name=name, x=list(xs), y=_values(domain, rng, count), color=color)
    for name, color in zip(names, _colours(config, rng, len(names)), strict=True)
  ]
  return ChartScene(
    kind=ChartKind.LINE,
    title=rng.choice(domain.titles),
    x_label=rng.choice(_TIME_LABELS),
    y_label=_y_label(domain),
    series=series,
    show_legend=multi,
  )


def _scatter_baseline(domain: Domain, config: StyleConfig, rng: random.Random, *, multi: bool) -> ChartScene:
  names = _series_names(domain, rng, multi=multi, palette_size=config.palette_size)
  count = rng.randint(8, 15)
  series = [
    Series(
      name=name,
      x=[round(rng.uniform(0.0, 100.0), 1) for _ in range(count)],
      y=_values(domain, rng, count),
      color=color,
    )
    for name, color in zip(names, _colours(config, rng, len(names)), strict=True)
  ]
  return ChartScene(
    kind=ChartKind.SCATTER,
    title=rng.choice(domain.titles),
    x_label=rng.choice(_SAMPLE_LABELS),  # a self-evident index axis: needs no unit, so axis-units stays satisfied
    y_label=_y_label(domain),
    series=series,
    show_legend=multi,
  )


def _pie_baseline(domain: Domain, config: StyleConfig, rng: random.Random, *, multi: bool) -> ChartScene:
  _ = multi  # a pie is always multi-slice; the single-group case never reaches here
  # Bound slice count by the palette size so every slice gets a distinct palette colour.
  count = rng.randint(3, min(5, len(domain.categories), config.palette_size))
  categories = list(rng.sample(domain.categories, count))
  colors = _colours(config, rng, count)
  return ChartScene(
    kind=ChartKind.PIE,
    title=rng.choice(domain.titles),
    x_label=None,
    y_label=None,
    series=[Series(name="share", x=categories, y=_values(domain, rng, count), color=colors[0])],
    show_legend=True,
    palette=colors,
  )


# gridline-weight compares the grid stroke to the *series line* weight, so it only applies where the data is a line: it
# is NA for bar, scatter, and pie (no line to compare against), served as a pass/fail only by the line type.
REGISTRY: tuple[ChartType, ...] = (
  ChartType(
    name="bar",
    kind=ChartKind.BAR,
    baseline=_bar_baseline,
    na_rules=frozenset({_GRIDWEIGHT}),
    supports_single_group=True,
  ),
  ChartType(
    name="line",
    kind=ChartKind.LINE,
    baseline=_line_baseline,
    na_rules=frozenset({"zero-baseline"}),
    supports_single_group=True,
  ),
  ChartType(
    name="scatter",
    kind=ChartKind.SCATTER,
    baseline=_scatter_baseline,
    na_rules=frozenset({"zero-baseline", _GRIDWEIGHT}),
    supports_single_group=True,
  ),
  ChartType(
    name="pie",
    kind=ChartKind.PIE,
    baseline=_pie_baseline,
    na_rules=frozenset({"axes-labeled", "axis-units", "zero-baseline", _GRIDLINE, _GRIDWEIGHT}),
    supports_single_group=False,
  ),
)


def _y_label(domain: Domain) -> str:
  return f"{domain.quantity} ({domain.unit})"


def _series_names(domain: Domain, rng: random.Random, *, multi: bool, palette_size: int) -> list[str]:
  # A multi-group chart picks 2-3 series (label-neutral: the legend stays a pass either way), capped by the palette size
  # so each series gets a distinct palette colour; a single-group chart picks one.
  if not multi:
    return [rng.choice(domain.series_names)]
  count = rng.randint(2, min(3, len(domain.series_names), palette_size))
  return list(rng.sample(domain.series_names, count))


def _colours(config: StyleConfig, rng: random.Random, count: int) -> list[str]:
  # Distinct compliant colours drawn from the config palette (count is bounded by the palette size by the callers).
  return rng.sample(config.palette, count)


def _values(domain: Domain, rng: random.Random, count: int) -> list[float]:
  low, high = domain.value_range
  return [round(rng.uniform(low, high), 1) for _ in range(count)]
