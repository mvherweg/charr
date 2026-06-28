"""The chart-type recipe registry: compose a cell, a chart type, a domain, and label-neutral jitter into a case.

This is the heart of the generator (docs/adr/0018). A chart type is **data**: a compliant-baseline builder, the set of
rules that are structurally ``not_applicable`` for it (``na_rules``), whether it can be drawn single-group (which makes
the legend NA), and a table of type-specific defect overrides (empty for the current four types - every defect for the
eight built-in rules turns out to operate on shared scene fields, so the shared :data:`GLOBAL_DEFECTS` table covers
them all). Labels stay correct by construction: a chart's verdict vector is a function of its ``(cell, type)`` and the
single defect injected, never of the seed, because all randomized knobs are label-neutral.

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
from charr_datagen.domains import DOMAINS, Domain
from charr_datagen.scenes import ChartKind, ChartScene, Series

ALL_RULES: tuple[RuleId, ...] = tuple(rule.id for rule in BUILTIN_RULES)

_LEGEND = "legend-when-multiple-groups"

# The palette compliant charts draw from, as (human name, hex). Names go into the checker config so the palette rule is
# judged against meaningful colors; hexes are what the backends draw. Off-palette charts use colors clearly outside it.
_PALETTE: tuple[tuple[str, str], ...] = (
  ("blue", "#1f77b4"),
  ("orange", "#ff7f0e"),
  ("green", "#2ca02c"),
  ("red", "#d62728"),
  ("purple", "#9467bd"),
)
_OFF_PALETTE: tuple[str, ...] = ("#ff1493", "#00ff00", "#00ffff", "#ff00ff", "#7fff00")  # hot pink, lime, cyan, ...

_FONT_SANS = "sans-serif"
_FONT_SERIF = "serif"
_FONT_EXPECTATION = "sans-serif"

_TIME_LABELS: tuple[str, ...] = ("Month", "Quarter", "Week", "Year", "Period")
_SAMPLE_LABELS: tuple[str, ...] = ("Sample", "Observation", "Trial", "Specimen", "Measurement")
_MARKERS: tuple[str, ...] = ("o", "s", "^", "D", "v")


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
  :param baseline: Builds a fully compliant scene of this type from ``(domain, rng, multi=...)``.
  :param na_rules: Rules structurally ``not_applicable`` for this type (e.g. a pie has no axes).
  :param supports_single_group: Whether the type can be drawn with one group, which makes the legend NA.
  :param extra_defects: Type-specific defect injectors, overriding :data:`GLOBAL_DEFECTS` (empty for the built-in four).
  """

  name: str
  kind: ChartKind
  baseline: Callable[..., ChartScene]
  na_rules: frozenset[RuleId]
  supports_single_group: bool
  extra_defects: dict[RuleId, Callable[[ChartScene], None]] = field(default_factory=dict)

  def defect_for(self, rule_id: RuleId) -> Callable[[ChartScene], None]:
    """Return the injector that makes ``rule_id`` fail for this type (type-specific override, else global)."""
    return self.extra_defects.get(rule_id, GLOBAL_DEFECTS[rule_id])


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

  The cell fixes the target rule and its verdict; the chart type (among those that can serve the cell), the domain, the
  numbers, and the cosmetic style are drawn from ``rng``. All of those are label-neutral, so the labels are exact.

  :param cell: The target ``(rule, polarity)`` to construct a chart for.
  :param rng: A seeded RNG owned by this case; drives all within-cell randomization.
  :return: The case, with labels known by construction.
  :raises ValueError: If no registered chart type can serve the cell (a registry/catalog drift the tests guard against).
  """
  capable = capable_types(cell)
  if not capable:
    msg = f"no chart type can serve cell {cell.label!r}"
    raise ValueError(msg)
  return assemble(cell, rng.choice(capable), rng)


def assemble(cell: Cell, chart_type: ChartType, rng: random.Random) -> Case:
  """Build a case for ``cell`` using a specific ``chart_type`` (the type-pinned core of :func:`build_case`).

  Exposed so tests can fix the chart type and assert the labels are correct and seed-invariant for that ``(cell, type)``
  pair. The label vector depends only on ``(cell, type)`` - never on ``rng``, which drives only label-neutral choices
  (domain, numbers, series count, cosmetics).

  :param cell: The target ``(rule, polarity)``.
  :param chart_type: The chart type to render with; must be able to serve ``cell``.
  :param rng: Seeded RNG for the label-neutral choices.
  :return: The case, with labels known by construction.
  """
  domain = rng.choice(DOMAINS)
  multi = _multi_for(cell)
  scene = chart_type.baseline(domain, rng, multi=multi)
  _jitter(scene, rng)
  labels = _baseline_labels(chart_type, multi=multi)
  if cell.polarity is Verdict.FAIL:
    chart_type.defect_for(cell.rule_id)(scene)
    labels.update(_FAIL_COLLATERAL.get(cell.rule_id, {}))
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


def _drop_title(scene: ChartScene) -> None:
  scene.title = None


def _drop_axis_labels(scene: ChartScene) -> None:
  scene.x_label = None
  scene.y_label = None


def _induce_overlap(scene: ChartScene) -> None:
  scene.overlap = True


def _off_palette(scene: ChartScene) -> None:
  for index, series in enumerate(scene.series):
    series.color = _OFF_PALETTE[index % len(_OFF_PALETTE)]
  if scene.palette:
    scene.palette = [_OFF_PALETTE[index % len(_OFF_PALETTE)] for index in range(len(scene.palette))]


def _use_serif(scene: ChartScene) -> None:
  scene.font_family = _FONT_SERIF


def _drop_units(scene: ChartScene) -> None:
  if scene.y_label and " (" in scene.y_label:
    scene.y_label = scene.y_label.split(" (")[0]


def _remove_legend(scene: ChartScene) -> None:
  scene.show_legend = False


def _nonzero_baseline(scene: ChartScene) -> None:
  scene.y_baseline_zero = False


GLOBAL_DEFECTS: dict[RuleId, Callable[[ChartScene], None]] = {
  "has-title": _drop_title,
  "axes-labeled": _drop_axis_labels,
  "no-overlapping-elements": _induce_overlap,
  "palette-compliance": _off_palette,
  "font-compliance": _use_serif,
  "axis-units": _drop_units,
  _LEGEND: _remove_legend,
  "zero-baseline": _nonzero_baseline,
}


# --- compliant baselines (one per kind; each returns a fully-passing scene of that kind) ---


def _bar_baseline(domain: Domain, rng: random.Random, *, multi: bool) -> ChartScene:
  count = rng.randint(3, min(5, len(domain.categories)))
  categories = list(rng.sample(domain.categories, count))
  names = _series_names(domain, rng, multi=multi)
  colors = _pick_colors(rng, len(names))
  series = [
    Series(name=name, x=list(categories), y=_values(domain, rng, count), color=color)
    for name, color in zip(names, colors, strict=True)
  ]
  return ChartScene(
    kind=ChartKind.BAR,
    title=rng.choice(domain.titles),
    x_label=domain.category_axis_label,
    y_label=_y_label(domain),
    series=series,
    show_legend=multi,
  )


def _line_baseline(domain: Domain, rng: random.Random, *, multi: bool) -> ChartScene:
  count = rng.randint(5, 8)
  xs = [float(step) for step in range(1, count + 1)]
  names = _series_names(domain, rng, multi=multi)
  colors = _pick_colors(rng, len(names))
  series = [
    Series(name=name, x=list(xs), y=_values(domain, rng, count), color=color)
    for name, color in zip(names, colors, strict=True)
  ]
  return ChartScene(
    kind=ChartKind.LINE,
    title=rng.choice(domain.titles),
    x_label=rng.choice(_TIME_LABELS),
    y_label=_y_label(domain),
    series=series,
    show_legend=multi,
  )


def _scatter_baseline(domain: Domain, rng: random.Random, *, multi: bool) -> ChartScene:
  count = rng.randint(8, 15)
  names = _series_names(domain, rng, multi=multi)
  colors = _pick_colors(rng, len(names))
  series = [
    Series(
      name=name,
      x=[round(rng.uniform(0.0, 100.0), 1) for _ in range(count)],
      y=_values(domain, rng, count),
      color=color,
    )
    for name, color in zip(names, colors, strict=True)
  ]
  return ChartScene(
    kind=ChartKind.SCATTER,
    title=rng.choice(domain.titles),
    x_label=rng.choice(_SAMPLE_LABELS),  # a self-evident index axis: needs no unit, so axis-units stays satisfied
    y_label=_y_label(domain),
    series=series,
    show_legend=multi,
  )


def _pie_baseline(domain: Domain, rng: random.Random, *, multi: bool) -> ChartScene:
  _ = multi  # a pie is always multi-slice; the single-group case never reaches here
  count = rng.randint(3, min(5, len(domain.categories)))
  categories = list(rng.sample(domain.categories, count))
  colors = _pick_colors(rng, count)
  return ChartScene(
    kind=ChartKind.PIE,
    title=rng.choice(domain.titles),
    x_label=None,
    y_label=None,
    series=[Series(name="share", x=categories, y=_values(domain, rng, count), color=colors[0])],
    show_legend=True,
    palette=colors,
  )


REGISTRY: tuple[ChartType, ...] = (
  ChartType(name="bar", kind=ChartKind.BAR, baseline=_bar_baseline, na_rules=frozenset(), supports_single_group=True),
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
    na_rules=frozenset({"zero-baseline"}),
    supports_single_group=True,
  ),
  ChartType(
    name="pie",
    kind=ChartKind.PIE,
    baseline=_pie_baseline,
    na_rules=frozenset({"axes-labeled", "axis-units", "zero-baseline"}),
    supports_single_group=False,
  ),
)


def _y_label(domain: Domain) -> str:
  return f"{domain.quantity} ({domain.unit})"


def _series_names(domain: Domain, rng: random.Random, *, multi: bool) -> list[str]:
  # A multi-group chart picks 2-3 series (label-neutral: the legend stays a pass either way); single picks one.
  if not multi:
    return [rng.choice(domain.series_names)]
  count = rng.randint(2, min(3, len(domain.series_names)))
  return list(rng.sample(domain.series_names, count))


def _pick_colors(rng: random.Random, count: int) -> list[str]:
  hexes = [hex_value for _, hex_value in _PALETTE]
  start = rng.randrange(len(hexes))
  return [hexes[(start + offset) % len(hexes)] for offset in range(count)]


def _values(domain: Domain, rng: random.Random, count: int) -> list[float]:
  low, high = domain.value_range
  return [round(rng.uniform(low, high), 1) for _ in range(count)]
