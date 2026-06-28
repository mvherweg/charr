"""Recipes: turn a stratification cell into a concrete, backend-agnostic chart scene plus its ground-truth labels.

The labels are known *by construction* (docs/adr/0015): each recipe starts from a fully compliant baseline chart whose
verdict for every rule is known, then introduces exactly one intended deviation for the cell's target rule (the
single-intended-issue MVP of docs/adr/0016). The scene it produces is a plain description of what to draw; turning that
into pixels is the backends' job (see :mod:`charr_datagen.rendering`), so the same recipe renders identically in intent
across matplotlib, seaborn, and plotly.

The palette and font the dataset is built against are fixed here and must be written into the dataset's ``charr.toml``
so the checker is told the same expectations the charts were drawn for; otherwise the palette/font rules would always be
``not_applicable``. See :func:`canonical_palette` and :func:`canonical_fonts`.
"""

import random
from dataclasses import dataclass, field
from enum import StrEnum

from charr.models import RuleId, Verdict
from charr.rules import BUILTIN_RULES

from charr_datagen.cells import Cell

# The palette the compliant charts are drawn from, as (human name, hex). The names go into the checker's config so the
# palette rule is judged against meaningful colors; the hexes are what the backends actually draw. Off-palette charts
# use colors clearly outside this set.
_PALETTE: tuple[tuple[str, str], ...] = (
  ("blue", "#1f77b4"),
  ("orange", "#ff7f0e"),
  ("green", "#2ca02c"),
  ("red", "#d62728"),
  ("purple", "#9467bd"),
)
_OFF_PALETTE: tuple[str, ...] = ("#ff1493", "#00ff00", "#00ffff", "#ff00ff", "#7fff00")  # hot pink, lime, cyan, ...

# The compliant charts use a sans-serif typeface; the font-violation charts use a serif one. The expectation handed to
# the checker is the generic family name, which a vision model can actually judge ("is this sans-serif?").
_FONT_SANS = "sans-serif"
_FONT_SERIF = "serif"
_FONT_EXPECTATION = "sans-serif"

_TITLES: tuple[str, ...] = (
  "Quarterly revenue",
  "Units sold by region",
  "Customer satisfaction",
  "Energy use by site",
  "Site traffic",
)
_CATEGORIES: tuple[str, ...] = (
  "North",
  "South",
  "East",
  "West",
  "Central",
  "Coastal",
  "Inland",
  "Metro",
  "Rural",
  "Harbor",
)
_LONG_CATEGORIES: tuple[str, ...] = (
  "North Atlantic Division",
  "Southern Coastal Region",
  "Eastern Metropolitan Area",
  "Western Industrial Belt",
  "Central Highlands District",
  "Greater Harbor Municipality",
)
_SERIES_NAMES: tuple[str, ...] = ("2023", "2024", "2025", "Plan", "Actual")
_Y_LABEL_WITH_UNITS = "Revenue (thousands USD)"
_Y_LABEL_NO_UNITS = "Revenue"
_X_LABEL_CATEGORY = "Region"
_X_LABEL_TIME = "Month"


class ChartType(StrEnum):
  """The kinds of charts the generator can draw."""

  BAR = "bar"
  LINE = "line"
  PIE = "pie"


@dataclass
class Series:
  """One data series within a scene: x positions (categories or numbers), y values, and a draw color."""

  name: str
  x: list[str] | list[float]
  y: list[float]
  color: str


@dataclass
class ChartScene:
  """A backend-agnostic description of a single chart to render.

  Every backend reads exactly these fields, so a scene renders with the same intent regardless of library. ``None`` for
  ``title``/``x_label``/``y_label`` means the element is deliberately absent (the by-construction way a labelling rule
  is made to fail).
  """

  chart_type: ChartType
  title: str | None
  x_label: str | None
  y_label: str | None
  series: list[Series]
  show_legend: bool
  font_family: str = _FONT_SANS
  y_baseline_zero: bool = True
  overlap: bool = False
  palette: list[str] = field(default_factory=list)


@dataclass
class Case:
  """A generated case: the scene to render and the ground-truth verdict for every rule."""

  scene: ChartScene
  labels: dict[RuleId, Verdict]


def canonical_palette() -> list[str]:
  """Return the palette color names to record in the dataset's checker config.

  :return: The human-readable color names the compliant charts use.
  """
  return [name for name, _ in _PALETTE]


def canonical_fonts() -> list[str]:
  """Return the font expectation to record in the dataset's checker config.

  :return: A single-element list naming the expected (sans-serif) typeface family.
  """
  return [_FONT_EXPECTATION]


def build_case(cell: Cell, rng: random.Random) -> Case:
  """Build the scene and ground-truth labels for one case in ``cell``, randomized within the cell.

  The cell fixes the target rule and its verdict; everything else (data values, category names, series count, palette
  choice, chart orientation) is drawn from ``rng`` so cases in the same cell vary while the labels stay exact.

  :param cell: The target ``(rule, polarity)`` to construct a chart for.
  :param rng: A seeded RNG owned by this case; drives all within-cell randomization.
  :return: The case, with labels known by construction.
  :raises ValueError: If the cell names a rule/polarity combination without a recipe.
  """
  if cell.polarity is Verdict.NOT_APPLICABLE:
    return _not_applicable_case(cell, rng)
  scene, labels = _compliant_bar(rng, multi=True)
  if cell.polarity is Verdict.PASS:
    return Case(scene=scene, labels=labels)
  _make_fail(scene, labels, cell.rule_id)
  return Case(scene=scene, labels=labels)


_RULE_IDS: tuple[RuleId, ...] = tuple(rule.id for rule in BUILTIN_RULES)


def _make_fail(scene: ChartScene, labels: dict[RuleId, Verdict], rule_id: RuleId) -> None:
  """Introduce exactly one violation for ``rule_id`` into an otherwise compliant bar scene, updating ``labels``."""
  if rule_id == "has-title":
    scene.title = None
  elif rule_id == "axes-labeled":
    # Drop both axis titles. Use a self-evident count axis so the missing y title does not also trip axis-units: the
    # only intended issue stays the missing labels.
    scene.x_label = None
    scene.y_label = None
    labels["axis-units"] = Verdict.NOT_APPLICABLE
  elif rule_id == "no-overlapping-elements":
    scene.overlap = True
    scene.series = [_relabel(series, _LONG_CATEGORIES) for series in scene.series]
  elif rule_id == "palette-compliance":
    for index, series in enumerate(scene.series):
      series.color = _OFF_PALETTE[index % len(_OFF_PALETTE)]
  elif rule_id == "font-compliance":
    scene.font_family = _FONT_SERIF
  elif rule_id == "axis-units":
    scene.y_label = _Y_LABEL_NO_UNITS
  elif rule_id == "legend-when-multiple-groups":
    scene.show_legend = False
  elif rule_id == "zero-baseline":
    scene.y_baseline_zero = False
  else:  # pragma: no cover - guarded by the cell catalog
    msg = f"no fail recipe for rule {rule_id!r}"
    raise ValueError(msg)
  labels[rule_id] = Verdict.FAIL


def _not_applicable_case(cell: Cell, rng: random.Random) -> Case:
  """Build a case whose target rule is genuinely ``not_applicable`` by choosing a chart type that excludes it."""
  if cell.rule_id in ("axes-labeled", "axis-units"):
    scene, labels = _compliant_pie(rng)
  elif cell.rule_id == "legend-when-multiple-groups":
    scene, labels = _compliant_bar(rng, multi=False)
  elif cell.rule_id == "zero-baseline":
    scene, labels = _compliant_line(rng)
  else:  # pragma: no cover - guarded by the cell catalog
    msg = f"no not_applicable recipe for rule {cell.rule_id!r}"
    raise ValueError(msg)
  labels[cell.rule_id] = Verdict.NOT_APPLICABLE
  return Case(scene=scene, labels=labels)


def _compliant_bar(rng: random.Random, *, multi: bool) -> tuple[ChartScene, dict[RuleId, Verdict]]:
  """Build a fully compliant bar chart. ``multi`` adds a second series and legend; single-series makes the legend NA."""
  count = rng.randint(3, 5)
  categories = list(rng.sample(_CATEGORIES, count))
  names = list(rng.sample(_SERIES_NAMES, 2)) if multi else [rng.choice(_SERIES_NAMES)]
  colors = _pick_colors(rng, len(names))
  series = [
    Series(name=name, x=list(categories), y=_values(rng, count), color=color)
    for name, color in zip(names, colors, strict=True)
  ]
  scene = ChartScene(
    chart_type=ChartType.BAR,
    title=rng.choice(_TITLES),
    x_label=_X_LABEL_CATEGORY,
    y_label=_Y_LABEL_WITH_UNITS,
    series=series,
    show_legend=multi,
  )
  labels = _all_pass()
  labels["legend-when-multiple-groups"] = Verdict.PASS if multi else Verdict.NOT_APPLICABLE
  return scene, labels


def _compliant_line(rng: random.Random) -> tuple[ChartScene, dict[RuleId, Verdict]]:
  """Build a compliant multi-series line chart over a time axis; zero-baseline is NA for this plot type."""
  count = rng.randint(5, 8)
  months = [float(month) for month in range(1, count + 1)]
  names = list(rng.sample(_SERIES_NAMES, 2))
  colors = _pick_colors(rng, len(names))
  series = [
    Series(name=name, x=list(months), y=_values(rng, count), color=color)
    for name, color in zip(names, colors, strict=True)
  ]
  scene = ChartScene(
    chart_type=ChartType.LINE,
    title=rng.choice(_TITLES),
    x_label=_X_LABEL_TIME,
    y_label=_Y_LABEL_WITH_UNITS,
    series=series,
    show_legend=True,
  )
  labels = _all_pass()
  labels["zero-baseline"] = Verdict.NOT_APPLICABLE
  return scene, labels


def _compliant_pie(rng: random.Random) -> tuple[ChartScene, dict[RuleId, Verdict]]:
  """Build a compliant pie chart: a legend names the slices; axes, axis units, and zero-baseline are all NA."""
  count = rng.randint(3, 5)
  categories = list(rng.sample(_CATEGORIES, count))
  values = _values(rng, count)
  colors = _pick_colors(rng, count)
  scene = ChartScene(
    chart_type=ChartType.PIE,
    title=rng.choice(_TITLES),
    x_label=None,
    y_label=None,
    series=[Series(name="share", x=categories, y=values, color=colors[0])],
    show_legend=True,
    palette=colors,
  )
  labels = _all_pass()
  labels["axes-labeled"] = Verdict.NOT_APPLICABLE
  labels["axis-units"] = Verdict.NOT_APPLICABLE
  labels["zero-baseline"] = Verdict.NOT_APPLICABLE
  return scene, labels


def _all_pass() -> dict[RuleId, Verdict]:
  return dict.fromkeys(_RULE_IDS, Verdict.PASS)


def _pick_colors(rng: random.Random, count: int) -> list[str]:
  hexes = [hex_value for _, hex_value in _PALETTE]
  start = rng.randrange(len(hexes))
  return [hexes[(start + offset) % len(hexes)] for offset in range(count)]


def _values(rng: random.Random, count: int) -> list[float]:
  return [float(rng.randint(10, 100)) for _ in range(count)]


def _relabel(series: Series, categories: tuple[str, ...]) -> Series:
  width = min(len(series.x), len(categories))
  return Series(name=series.name, x=list(categories[:width]), y=series.y[:width], color=series.color)
