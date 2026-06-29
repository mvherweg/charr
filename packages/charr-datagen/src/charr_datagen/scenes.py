"""The backend-agnostic description of a single chart to render.

A :class:`ChartScene` is plain data: every rendering backend (see :mod:`charr_datagen.rendering`) reads exactly these
fields, so a scene renders with the same intent regardless of library. The recipes in :mod:`charr_datagen.recipes`
produce scenes; the split between fields that bear on a verdict (title / axis-label / units presence, palette and font,
baseline) and fields that are purely cosmetic (grid, marker, the numbers) is what lets variety grow without disturbing
the ground-truth labels (docs/adr/0018).
"""

from dataclasses import dataclass, field
from enum import StrEnum


class ChartKind(StrEnum):
  """The visual kind a backend draws. A recipe maps to one kind; several recipes may share a kind later."""

  BAR = "bar"
  LINE = "line"
  PIE = "pie"
  SCATTER = "scatter"


class DataLabels(StrEnum):
  """How a scene draws per-element value labels - the axis the no-overlapping-elements rule turns on.

  The labels always carry real chart values (a number or a category share), never text that names the verdict, so the
  rule can only be judged by *seeing* whether they collide, not by reading them. ``SEPARATED`` and ``COLLIDING`` are the
  two polarities of that rule's contrast and differ only in layout; ``NONE`` is every other chart, which simply omits
  value labels.
  """

  NONE = "none"
  SEPARATED = "separated"
  COLLIDING = "colliding"


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

  ``None`` for ``title`` / ``x_label`` / ``y_label`` means the element is deliberately absent (the by-construction way
  a labelling rule is made to fail). ``data_labels`` drives the no-overlapping-elements rule (see :class:`DataLabels`).
  ``background`` is the plot canvas colour and drives the background-series-contrast rule: the dataset norm is white,
  a violation sets it to a plotted series' colour (so that series blends in). ``grid`` and ``marker`` are cosmetic,
  label-neutral jitter.
  """

  kind: ChartKind
  title: str | None
  x_label: str | None
  y_label: str | None
  series: list[Series]
  show_legend: bool
  font_family: str = "sans-serif"
  y_baseline_zero: bool = True
  data_labels: DataLabels = DataLabels.NONE
  background: str = "#ffffff"
  grid: bool = True
  marker: str = "o"
  palette: list[str] = field(default_factory=list)
