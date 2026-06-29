"""Orchestration: turn a sample budget into a multi-config sweep of self-describing labeled datasets on disk.

This is the policy layer over the pure pieces. It decides the active library set (docs/adr/0013), samples N independent
style-configs (docs/adr/0019), and for each config writes a *self-describing* dataset under ``out_dir/config-NN/``: the
images, the JSONL manifest of ground-truth labels, the ``charr.toml`` of that config's palette and fonts (so the
palette/font rules are judged against the expectations the charts were drawn for), and a ``meta.json``. A run-level
``meta.json`` at ``out_dir`` indexes the configs.

Each config independently stratifies and allocates the budget across cells (docs/adr/0014), so every ``config-NN/`` is a
valid standalone eval unit; ``charr-eval out_dir/*/labels.jsonl`` unions them. Font-compliance cells are kept off the
plotly backend, and any plotly image carries ``font-compliance: not_applicable``, because kaleido cannot be trusted to
render a bundled font faithfully (docs/adr/0021). A run is deterministic in ``(samples, configs, seed)`` for a fixed
active library set.
"""

import json
import random
from dataclasses import dataclass
from pathlib import Path

import charr
from charr.models import Verdict

from charr_datagen import __version__
from charr_datagen.cells import Allocation, Cell, allocate, build_cells
from charr_datagen.configs import StyleConfig, sample_configs
from charr_datagen.dataset import ManifestRecord, write_manifest
from charr_datagen.errors import DatagenError
from charr_datagen.recipes import build_case
from charr_datagen.rendering import ALL_LIBRARIES, MANDATORY_LIBRARIES, Backend, get_backend, plotly_usable

MANIFEST_NAME = "labels.jsonl"
CONFIG_NAME = "charr.toml"
META_NAME = "meta.json"
IMAGES_DIRNAME = "images"

_FONT_RULE = "font-compliance"

__all__ = [
  "CONFIG_NAME",
  "IMAGES_DIRNAME",
  "MANIFEST_NAME",
  "META_NAME",
  "ConfigResult",
  "DatagenError",
  "GenerationResult",
  "generate",
  "resolve_libraries",
]


@dataclass(frozen=True)
class ConfigResult:
  """Summary of one style-config's dataset within a run."""

  config: StyleConfig
  out_dir: Path
  image_count: int


@dataclass(frozen=True)
class GenerationResult:
  """Summary of a completed run across every style-config, for the CLI to report."""

  out_dir: Path
  configs: tuple[ConfigResult, ...]
  allocation: Allocation
  libraries: tuple[str, ...]
  messages: tuple[str, ...]

  @property
  def image_count(self) -> int:
    """Return the total number of images written across all configs.

    :return: Sum of the per-config image counts.
    """
    return sum(result.image_count for result in self.configs)

  @property
  def uncovered(self) -> tuple[Cell, ...]:
    """Return the cells the budget could not cover (identical for every config; empty unless under-budget).

    :return: The uncovered cells, in priority order.
    """
    return self.allocation.uncovered


@dataclass(frozen=True)
class _RunContext:
  """The run-invariant inputs shared by every config's generation pass (bundled to keep helpers few-argument)."""

  allocation: Allocation
  active: list[str]
  backends: dict[str, Backend]
  seed: int


def generate(  # noqa: PLR0913 - these are the generator's public knobs; bundling them would obscure the CLI surface.
  out_dir: Path,
  *,
  samples: int | None = None,
  configs: int = 1,
  seed: int = 0,
  libraries: list[str] | None = None,
  strict_coverage: bool = False,
) -> GenerationResult:
  """Generate a multi-config sweep of labeled datasets under ``out_dir`` and return a summary.

  :param out_dir: Directory to write the run into (created if absent); each config writes a ``config-NN/`` dataset.
  :param samples: Number of cases *per config*; defaults to one per cell (full coverage). Total images are
    ``samples * configs``.
  :param configs: Number of independent style-configs to sample (default 1).
  :param seed: Base seed; the run is reproducible for a fixed active library set.
  :param libraries: Explicit library set to pin; ``None`` uses matplotlib + seaborn plus plotly when usable.
  :param strict_coverage: When the budget cannot cover every cell, error instead of warning and proceeding.
  :return: The generation summary (per-config results, allocation, active libraries, messages).
  :raises DatagenError: On an unsatisfiable library pin, a plotly-only pin (no faithful font backend), or under-budget
    with ``strict_coverage``.
  """
  cells = build_cells()
  active, messages = resolve_libraries(libraries)
  budget = len(cells) if samples is None else samples
  allocation = allocate(budget, cells)
  messages = [*messages, *_coverage_messages(allocation, strict=strict_coverage)]

  _ensure_parent(out_dir)
  out_dir.mkdir(exist_ok=True)
  context = _RunContext(
    allocation=allocation, active=active, backends={name: get_backend(name) for name in active}, seed=seed
  )
  style_configs = sample_configs(configs, seed)

  config_results = [
    _generate_one(out_dir / config.name, config, index, context) for index, config in enumerate(style_configs)
  ]
  result = GenerationResult(
    out_dir=out_dir,
    configs=tuple(config_results),
    allocation=allocation,
    libraries=tuple(active),
    messages=tuple(messages),
  )
  _write_run_meta(out_dir / META_NAME, result, seed=seed, samples=budget, requested=libraries)
  return result


def resolve_libraries(requested: list[str] | None) -> tuple[list[str], list[str]]:
  """Decide the active library set and any operator-facing messages.

  With no request, matplotlib and seaborn are always active and plotly joins them when usable, otherwise it drops with a
  logged message (graceful degradation). An explicit ``--libraries`` pin is honored exactly; pinning plotly when its
  static export is unavailable is an error (docs/adr/0013), and pinning *only* plotly is an error because the
  font-compliance cells need a backend that renders bundled fonts faithfully (docs/adr/0021).

  :param requested: The explicit library set, or ``None`` for the default policy.
  :return: ``(active library names, messages)``.
  :raises DatagenError: If a requested library is unknown, plotly is pinned but unusable, or no non-plotly backend is
    active.
  """
  if requested:
    unknown = [name for name in requested if name not in ALL_LIBRARIES]
    if unknown:
      msg = f"unknown rendering libraries {unknown}; known: {', '.join(ALL_LIBRARIES)}"
      raise DatagenError(msg)
    active = list(dict.fromkeys(requested))
    if "plotly" in active and not plotly_usable():
      msg = "plotly was pinned via --libraries but its static export is unavailable; install 'charr-datagen[plotly]'"
      raise DatagenError(msg)
    if not any(name != "plotly" for name in active):
      msg = "at least one non-plotly backend (matplotlib or seaborn) is required: plotly cannot render bundled fonts"
      raise DatagenError(msg)
    return active, []
  active = list(MANDATORY_LIBRARIES)
  if plotly_usable():
    active.append("plotly")
    return active, []
  message = f"plotly disabled: kaleido static export unavailable; rendering with {', '.join(MANDATORY_LIBRARIES)}"
  return active, [message]


def _generate_one(config_dir: Path, config: StyleConfig, config_index: int, context: _RunContext) -> ConfigResult:
  """Render and write one style-config's self-describing dataset under ``config_dir``."""
  images_dir = _prepare_config_dir(config_dir)
  records: list[ManifestRecord] = []
  index = 0
  for cell_index, (cell, count) in enumerate(zip(context.allocation.cells, context.allocation.counts, strict=True)):
    eligible = _eligible_libraries(cell, context.active)
    for case_index in range(count):
      library = eligible[case_index % len(eligible)]
      case = build_case(cell, config, _case_rng(context.seed, config_index, cell_index, case_index))
      if library == "plotly":
        case.labels[_FONT_RULE] = Verdict.NOT_APPLICABLE  # kaleido cannot be trusted to render the bundled font
      filename = f"{index:04d}-{cell.label}-{library}.png"
      context.backends[library].render(case.scene, images_dir / filename)
      records.append(ManifestRecord(image=f"{IMAGES_DIRNAME}/{filename}", library=library, labels=case.labels))
      index += 1
  write_manifest(config_dir / MANIFEST_NAME, records)
  _write_config(config_dir / CONFIG_NAME, config)
  _write_config_meta(config_dir / META_NAME, config, context.allocation)
  return ConfigResult(config=config, out_dir=config_dir, image_count=len(records))


def _eligible_libraries(cell: Cell, active: list[str]) -> list[str]:
  """Return the libraries that may render ``cell``: font-compliance cells exclude plotly (docs/adr/0021)."""
  if cell.rule_id == _FONT_RULE:
    return [name for name in active if name != "plotly"]
  return active


def _ensure_parent(out_dir: Path) -> None:
  """Fail loudly if ``out_dir``'s parent does not exist, so a typo'd path does not fabricate a deep tree."""
  if not out_dir.parent.is_dir():
    msg = f"output parent directory does not exist: {out_dir.parent}"
    raise DatagenError(msg)


def _prepare_config_dir(config_dir: Path) -> Path:
  """Create a config's dataset directory and its ``images/`` subdir, returning the images path."""
  config_dir.mkdir(exist_ok=True)
  images_dir = config_dir / IMAGES_DIRNAME
  images_dir.mkdir(exist_ok=True)
  return images_dir


def _coverage_messages(allocation: Allocation, *, strict: bool) -> list[str]:
  """Warn (or, under ``strict``, error) when the per-config budget leaves cells uncovered."""
  uncovered = allocation.uncovered
  if not uncovered:
    return []
  labels = ", ".join(cell.label for cell in uncovered)
  minimum = allocation.min_for_full_coverage
  if strict:
    msg = (
      f"under-budget: {len(uncovered)} cell(s) uncovered; raise --samples to at least {minimum}. Uncovered: {labels}"
    )
    raise DatagenError(msg)
  return [f"under-budget: {len(uncovered)} cell(s) not sampled (need samples >= {minimum} for full coverage): {labels}"]


def _case_rng(seed: int, config_index: int, cell_index: int, case_index: int) -> random.Random:
  # String seed so the RNG is deterministic regardless of PYTHONHASHSEED (random.Random hashes str/bytes with sha512).
  # Pseudo-randomness is exactly what we want here (reproducible synthetic data), not cryptographic strength.
  return random.Random(f"{seed}:{config_index}:{cell_index}:{case_index}")  # noqa: S311 - reproducible data, not security


def _write_config(path: Path, config: StyleConfig) -> None:
  """Write the dataset's ``charr.toml`` so the checker is told the palette and fonts the charts were drawn against."""
  palette = json.dumps(list(config.palette))
  fonts = json.dumps(config.font_names())
  body = (
    "# Written by charr-datagen. This is the checker config this config-NN dataset was generated against;\n"
    "# charr-eval discovers it next to the manifest so the palette and font rules are judged against the same\n"
    "# expectations the charts were drawn for. Colours are sRGB hex; fonts are family names.\n"
    f"palette = {palette}\n"
    f"fonts = {fonts}\n"
  )
  path.write_text(body, encoding="ascii")


def _write_config_meta(path: Path, config: StyleConfig, allocation: Allocation) -> None:
  """Write a config's ``meta.json``: its sampled palette and fonts, plus the realized cell allocation."""
  meta = {
    "config": config.name,
    "palette": list(config.palette),
    "fonts": config.font_names(),
    "cells": [
      {"rule": cell.rule_id, "polarity": cell.polarity.value, "count": count}
      for cell, count in zip(allocation.cells, allocation.counts, strict=True)
    ],
    "uncovered": [cell.label for cell in allocation.uncovered],
  }
  path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="ascii")


def _write_run_meta(
  path: Path, result: GenerationResult, *, seed: int, samples: int, requested: list[str] | None
) -> None:
  """Write the run-level ``meta.json`` indexing the configs and recording the reproducibility inputs."""
  meta = {
    "charr_datagen_version": __version__,
    "charr_version": charr.__version__,
    "seed": seed,
    "samples_per_config": samples,
    "config_count": len(result.configs),
    "image_count": result.image_count,
    "libraries": list(result.libraries),
    "libraries_requested": requested,
    "configs": [
      {"config": item.config.name, "palette": list(item.config.palette), "fonts": item.config.font_names()}
      for item in result.configs
    ],
    "uncovered": [cell.label for cell in result.uncovered],
    "min_samples_for_full_coverage": result.allocation.min_for_full_coverage,
    "messages": list(result.messages),
  }
  path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="ascii")
