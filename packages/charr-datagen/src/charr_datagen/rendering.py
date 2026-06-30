"""Rendering backends: draw a :class:`~charr_datagen.scenes.ChartScene` to a PNG with a named library.

This module is mechanics only: given a library name it hands back a backend that renders a scene. matplotlib and seaborn
are always available (base dependencies); plotly is optional and may not import or may lack a working static-export path
(kaleido + headless Chromium), so :func:`plotly_usable` probes it with a real one-pixel export. The policy decision of
which libraries a run actually uses lives in :mod:`charr_datagen.generate` (docs/adr/0013).

Image bytes are not part of any contract: they vary by library, version, and platform. Only the *intent* encoded in the
scene is stable, which is why the test suite asserts allocation and labels rather than pixels.
"""

import matplotlib as mpl

mpl.use("Agg")  # headless, deterministic PNG path; must precede the pyplot import.

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib import font_manager
from matplotlib.axes import Axes

from charr_datagen.errors import DatagenError
from charr_datagen.fonts import SUPPORTED_FONTS, font_path
from charr_datagen.scenes import ChartKind, ChartScene, DataLabels

_SeabornStyle = Literal["white", "dark", "whitegrid", "darkgrid", "ticks"]

MANDATORY_LIBRARIES: tuple[str, ...] = ("matplotlib", "seaborn")
OPTIONAL_LIBRARIES: tuple[str, ...] = ("plotly",)
ALL_LIBRARIES: tuple[str, ...] = MANDATORY_LIBRARIES + OPTIONAL_LIBRARIES

# plotly uses CSS marker-symbol names; map the matplotlib markers the scenes carry onto them.
_MAX_DATA_LABELS = 5  # representative value labels drawn for the no-overlapping-elements rule (both polarities)

_PLOTLY_MARKERS: dict[str, str] = {
  "o": "circle",
  "s": "square",
  "^": "triangle-up",
  "D": "diamond",
  "v": "triangle-down",
}


@dataclass(frozen=True)
class Backend:
  """A named renderer: ``render(scene, out)`` writes a PNG for ``scene`` to ``out``."""

  name: str
  render: Callable[[ChartScene, Path], None]


def get_backend(name: str) -> Backend:
  """Return the rendering backend for a library name.

  :param name: One of :data:`ALL_LIBRARIES`.
  :return: The backend that renders with that library.
  :raises ValueError: If ``name`` is not a known library.
  """
  if name == "matplotlib":
    return Backend(name, lambda scene, out: _draw_matplotlib(scene, out, seaborn_style=None))
  if name == "seaborn":
    return Backend(name, lambda scene, out: _draw_matplotlib(scene, out, seaborn_style="whitegrid"))
  if name == "plotly":
    return Backend(name, _draw_plotly)
  msg = f"unknown rendering library: {name!r} (known: {', '.join(ALL_LIBRARIES)})"
  raise ValueError(msg)


def plotly_usable() -> bool:
  """Report whether plotly can actually export a static PNG in this environment.

  Probes both the import and a real one-pixel export, so a plotly install without a working kaleido/Chromium reports
  unusable rather than crashing mid-run.

  :return: True when plotly + a static-export path are available.
  """
  try:
    import plotly.graph_objects as go  # noqa: PLC0415  # pyright: ignore[reportMissingImports] - optional extra
  except ImportError:
    return False
  try:
    go.Figure(data=[go.Bar(x=[0], y=[0])]).to_image(format="png", width=8, height=8)
  except Exception:  # noqa: BLE001 - any export failure (missing kaleido/Chromium) means "not usable"
    return False
  return True


def _draw_matplotlib(scene: ChartScene, out: Path, *, seaborn_style: _SeabornStyle | None) -> None:
  """Render ``scene`` with matplotlib, optionally under a seaborn theme for visual variety."""
  with plt.rc_context():
    if seaborn_style is not None:
      sns.set_theme(style=seaborn_style)
    plt.rcParams["font.family"] = scene.font_family
    fig, ax = plt.subplots(figsize=(6.0, 4.0), dpi=100)
    fig.set_facecolor(scene.background)
    ax.set_facecolor(scene.background)  # the plot canvas a series must contrast with (background-series-contrast rule)
    if scene.kind is ChartKind.BAR:
      _mpl_bars(ax, scene)
    elif scene.kind is ChartKind.LINE:
      _mpl_lines(ax, scene)
    elif scene.kind is ChartKind.SCATTER:
      _mpl_scatter(ax, scene)
    else:
      _mpl_pie(ax, scene)
    if scene.title is not None:
      ax.set_title(scene.title)
    _mpl_data_labels(ax, scene)
    fig.tight_layout()
    fig.savefig(out, format="png", facecolor=scene.background)  # keep the canvas colour in the saved PNG
    plt.close(fig)


def _mpl_bars(ax: Axes, scene: ChartScene) -> None:
  categories = [str(value) for value in scene.series[0].x]
  positions = np.arange(len(categories))
  group_count = len(scene.series)
  width = 0.8 / group_count
  for index, series in enumerate(scene.series):
    offset = (index - (group_count - 1) / 2) * width
    ax.bar(positions + offset, series.y, width=width, label=series.name, color=series.color)
  ax.set_xticks(positions)
  ax.set_xticklabels(categories, rotation=0)
  _mpl_axes(ax, scene)


def _mpl_lines(ax: Axes, scene: ChartScene) -> None:
  for series in scene.series:
    ax.plot(series.x, series.y, marker=scene.marker, label=series.name, color=series.color)
  _mpl_axes(ax, scene)


def _mpl_scatter(ax: Axes, scene: ChartScene) -> None:
  for series in scene.series:
    ax.scatter(series.x, series.y, marker=scene.marker, label=series.name, color=series.color)
  _mpl_axes(ax, scene)


def _mpl_pie(ax: Axes, scene: ChartScene) -> None:
  series = scene.series[0]
  categories = [str(value) for value in series.x]
  wedges, _ = ax.pie(series.y, colors=scene.palette or None)
  if scene.show_legend:
    ax.legend(wedges, categories, loc="center left", bbox_to_anchor=(1.0, 0.5))
  ax.set_aspect("equal")


def _mpl_axes(ax: Axes, scene: ChartScene) -> None:
  if scene.x_label is not None:
    ax.set_xlabel(scene.x_label)
  if scene.y_label is not None:
    ax.set_ylabel(scene.y_label)
  if scene.y_baseline_zero:
    ax.set_ylim(bottom=0)
  else:
    lowest = min(value for series in scene.series for value in series.y)
    ax.set_ylim(bottom=lowest * 0.85)
  ax.grid(visible=scene.grid)
  if scene.show_legend:
    ax.legend()


def _mpl_data_labels(ax: Axes, scene: ChartScene) -> None:
  """Draw the first series' real value labels per :func:`_data_label_layout` (the no-overlapping-elements rule)."""
  if scene.data_labels is DataLabels.NONE:
    return
  anchors, fontsize = _data_label_layout(scene)
  for x, y, text in anchors:
    ax.text(x, y, text, transform=ax.transAxes, ha="center", va="center", fontsize=fontsize)


def _data_label_layout(scene: ChartScene) -> tuple[list[tuple[float, float, str]], int]:
  """Axes-fraction ``(x, y, text)`` anchors plus a font size for the first series' value labels, shared by all backends.

  Both polarities draw the same real values, so neither the presence nor the content of the labels can leak the
  no-overlapping verdict - only the layout does. ``COLLIDING`` stacks them at one x in a tight band so they pile into a
  guaranteed collision; ``SEPARATED`` spreads them across a clear band. Positioning by figure fraction (not by the
  backend's own label auto-placement) keeps the collision true by construction on every backend.
  """
  # Cap to a few representative points so the SEPARATED row stays unambiguously clear even on a dense scatter; both
  # polarities draw the same count, so the cap does not become a presence cue.
  texts = [f"{value:g}" for value in scene.series[0].y[:_MAX_DATA_LABELS]]
  count = len(texts)
  if scene.data_labels is DataLabels.COLLIDING:
    ys = np.linspace(0.80, 0.90, count)
    return [(0.5, float(y), text) for y, text in zip(ys, texts, strict=True)], 14
  xs = np.linspace(0.07, 0.93, count)
  return [(float(x), 0.9, text) for x, text in zip(xs, texts, strict=True)], 9


def _draw_plotly(scene: ChartScene, out: Path) -> None:
  """Render ``scene`` with plotly + kaleido; only called when :func:`plotly_usable` returned True."""
  import plotly.graph_objects as go  # noqa: PLC0415  # pyright: ignore[reportMissingImports] - optional extra

  if scene.kind is ChartKind.PIE:
    series = scene.series[0]
    traces: list[object] = [
      go.Pie(labels=[str(value) for value in series.x], values=series.y, marker={"colors": scene.palette or None}),
    ]
  elif scene.kind is ChartKind.LINE:
    symbol = _PLOTLY_MARKERS.get(scene.marker, "circle")
    traces = [
      go.Scatter(
        x=series.x,
        y=series.y,
        mode="lines+markers",
        name=series.name,
        line={"color": series.color},
        marker={"symbol": symbol},
      )
      for series in scene.series
    ]
  elif scene.kind is ChartKind.SCATTER:
    symbol = _PLOTLY_MARKERS.get(scene.marker, "circle")
    traces = [
      go.Scatter(
        x=series.x, y=series.y, mode="markers", name=series.name, marker={"color": series.color, "symbol": symbol}
      )
      for series in scene.series
    ]
  else:
    traces = [
      go.Bar(x=series.x, y=series.y, name=series.name, marker={"color": series.color}) for series in scene.series
    ]
  figure = go.Figure(data=traces)
  figure.update_layout(
    title=scene.title,
    xaxis_title=scene.x_label,
    yaxis_title=scene.y_label,
    showlegend=scene.show_legend,
    font={"family": scene.font_family},
    paper_bgcolor=scene.background,
    plot_bgcolor=scene.background,  # the canvas a series must contrast with (background-series-contrast rule)
    width=600,
    height=400,
  )
  figure.update_xaxes(showgrid=scene.grid)
  figure.update_yaxes(showgrid=scene.grid)
  if scene.kind is ChartKind.BAR and not scene.y_baseline_zero:
    lowest = min(value for series in scene.series for value in series.y)
    highest = max(value for series in scene.series for value in series.y)
    figure.update_yaxes(range=[lowest * 0.85, highest * 1.05])
  if scene.data_labels is not DataLabels.NONE:
    anchors, fontsize = _data_label_layout(scene)
    for x, y, text in anchors:
      figure.add_annotation(x=x, y=y, xref="paper", yref="paper", showarrow=False, text=text, font={"size": fontsize})
  figure.write_image(out, format="png")


def _register_bundled_fonts() -> None:
  """Register every bundled font with matplotlib and verify none silently falls back to a different family.

  matplotlib renders a registered font faithfully, so a chart drawn in an approved font really shows it - which is why
  font-compliance ground truth is trusted on matplotlib/seaborn (and held ``not_applicable`` on plotly, docs/adr/0021).
  A missing file or a fallback to a different family raises rather than mislabelling an image.
  """
  for font in SUPPORTED_FONTS:
    path = font_path(font)
    if not path.is_file():
      msg = f"bundled font missing: {path}"
      raise DatagenError(msg)
    font_manager.fontManager.addfont(str(path))
  for font in SUPPORTED_FONTS:
    try:
      resolved = font_manager.findfont(font.name, fallback_to_default=False)
    except ValueError as exc:
      msg = f"bundled font {font.name!r} did not register with matplotlib"
      raise DatagenError(msg) from exc
    family = font_manager.FontProperties(fname=resolved).get_name()
    if family != font.name:
      msg = f"font {font.name!r} resolves to {family!r}: registration failed or a silent fallback occurred"
      raise DatagenError(msg)


_register_bundled_fonts()
