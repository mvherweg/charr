"""The built-in rule catalog and the selection logic that turns config into the list of rules to run.

The catalog is plain data (see project.md for the documented rules). Selection is pure: given the user's enable/disable
choices it returns the ordered rules to send to the model. Custom user-defined rules are a later increment; the shape
here (a flat list of ``Rule`` plus an id lookup) is what they will extend.
"""

from charr.models import Rule, RuleId

# The order here is the order rules are presented to the model and reported back, so keep it stable and intentional.
BUILTIN_RULES: tuple[Rule, ...] = (
  Rule(
    id="has-title",
    summary="Chart has a clear title.",
    prompt="The chart must have a clear, present title describing what it shows. Pass only if a title is visible.",
  ),
  Rule(
    id="axes-labeled",
    summary="Axes carry labels where applicable.",
    prompt=(
      "Each axis that needs a label must carry one. Pass if every applicable axis is labeled; fail if an axis that "
      "should be labeled is not. Use not_applicable only when the chart type has no axes (e.g. a pie chart)."
    ),
  ),
  Rule(
    id="no-overlapping-elements",
    summary="No overlapping or colliding elements.",
    prompt=(
      "Text and chart elements must not weirdly overlap or collide; labels, ticks, and the legend should be cleanly "
      "separated and readable. Fail if elements overlap in a way that hurts legibility."
    ),
  ),
  Rule(
    id="palette-compliance",
    summary="Colors match the configured palette.",
    prompt=(
      "The chart's colors must come from the allowed palette: {palette}. Fail if clearly off-palette colors are used. "
      "Use not_applicable when no palette is configured or the chart is effectively monochrome."
    ),
    na_without="palette",
  ),
  Rule(
    id="font-compliance",
    summary="Fonts match the configured expectation.",
    prompt=(
      "The chart's text must use the expected font(s): {fonts}. Fail if the typeface clearly differs. Use "
      "not_applicable when no fonts are configured or the font cannot be judged from the image."
    ),
    na_without="fonts",
  ),
  Rule(
    id="axis-units",
    summary="Numeric axes state units when not self-evident.",
    prompt=(
      "A numeric axis must state its units when they are not self-evident. An axis that is obviously something else "
      "(e.g. dates, categories) does not need units: return not_applicable for it. Fail when a numeric quantity lacks "
      "units that a reader would need."
    ),
  ),
  Rule(
    id="legend-when-multiple-groups",
    summary="Legend present when multiple groups are shown.",
    prompt=(
      "When the chart shows more than one group or series, a legend identifying them must be present. Use "
      "not_applicable when only a single group/series is shown. Fail when multiple groups are shown without a legend."
    ),
  ),
  Rule(
    id="zero-baseline",
    summary="Zero baseline where omitting it would mislead.",
    prompt=(
      "For plot types where a non-zero baseline misleads (notably bar charts), the value axis must start at zero. Use "
      "not_applicable for plot types where a zero baseline is not expected (e.g. line charts of a bounded range). Fail "
      "when a misleading non-zero baseline is used."
    ),
  ),
  Rule(
    id="background-series-contrast",
    summary="Background contrasts with the series colors.",
    prompt=(
      "The plot background must contrast clearly with every plotted data series, so no series blends into it. Fail "
      "when a series color is so close to the background color that the series is hard to make out against it. Judge "
      "the data marks (bars, lines, points, pie slices) against the background, not the axes or gridlines."
    ),
  ),
  Rule(
    id="gridline-series-contrast",
    summary="Gridlines stay distinct from the series colors.",
    prompt=(
      "Gridlines, when present, must stay visually distinct from the plotted data series; a gridline sharing a "
      "series' color reads as data. Fail when a gridline color matches or is very close to a plotted series color. "
      "Pass when there are no gridlines or every gridline is clearly distinct from the series. Use not_applicable only "
      "for charts with no cartesian grid (e.g. pie charts)."
    ),
  ),
)

BUILTIN_RULES_BY_ID: dict[RuleId, Rule] = {rule.id: rule for rule in BUILTIN_RULES}


def select_enabled_rules(enable: list[RuleId], disable: list[RuleId]) -> list[Rule]:
  """Resolve which built-in rules to run, preserving catalog order.

  When ``enable`` is empty each rule's ``enabled_by_default`` applies; when non-empty it is an explicit allow-list.
  ``disable`` always wins.

  :param enable: Rule ids to enable; empty means use each rule's default.
  :param disable: Rule ids to disable; takes precedence over ``enable``.
  :return: The enabled rules, in catalog order.
  :raises KeyError: If an id in ``enable`` or ``disable`` is not a known built-in rule.
  """
  for rule_id in (*enable, *disable):
    if rule_id not in BUILTIN_RULES_BY_ID:
      msg = f"unknown rule id: {rule_id!r}"
      raise KeyError(msg)
  disabled = set(disable)
  selected: list[Rule] = []
  for rule in BUILTIN_RULES:
    if rule.id in disabled:
      continue
    wanted = rule.id in enable if enable else rule.enabled_by_default
    if wanted:
      selected.append(rule)
  return selected
