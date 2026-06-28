"""Orchestration: turn a sample budget into a self-describing labeled dataset on disk.

This is the policy layer over the pure pieces. It decides the active library set (docs/adr/0013), apportions the budget
across cells (docs/adr/0014), renders each case, and writes a dataset that is *self-describing*: images, the JSONL
manifest of ground-truth labels, the ``charr.toml`` the charts were drawn against (so the palette/font rules are judged
against the same expectations), and a ``meta.json`` recording the seed and active libraries for reproducibility.

Everything here is deterministic in ``(samples, seed, config)`` for a fixed active library set: the allocation, the
per-case RNG seeds, and the round-robin library assignment within each cell.
"""

import json
import random
from dataclasses import dataclass
from pathlib import Path

import charr
from charr.models import CharrError

from charr_datagen import __version__
from charr_datagen.cases import build_case, canonical_fonts, canonical_palette
from charr_datagen.cells import Allocation, Cell, allocate, build_cells
from charr_datagen.dataset import ManifestRecord, write_manifest
from charr_datagen.rendering import ALL_LIBRARIES, MANDATORY_LIBRARIES, get_backend, plotly_usable

MANIFEST_NAME = "labels.jsonl"
CONFIG_NAME = "charr.toml"
META_NAME = "meta.json"
IMAGES_DIRNAME = "images"


class DatagenError(CharrError):
  """Raised when a generation run cannot proceed (bad library pin, or under-budget under ``--strict-coverage``)."""


@dataclass(frozen=True)
class GenerationResult:
  """Summary of a completed run, for the CLI to report."""

  out_dir: Path
  allocation: Allocation
  libraries: tuple[str, ...]
  image_count: int
  messages: tuple[str, ...]

  @property
  def uncovered(self) -> tuple[Cell, ...]:
    """Return the cells the budget could not cover (empty unless ``samples`` was below the cell count).

    :return: The uncovered cells, in priority order.
    """
    return self.allocation.uncovered


def generate(
  out_dir: Path,
  *,
  samples: int | None = None,
  seed: int = 0,
  libraries: list[str] | None = None,
  strict_coverage: bool = False,
) -> GenerationResult:
  """Generate a labeled dataset under ``out_dir`` and return a summary.

  :param out_dir: Directory to write the dataset into (created if absent).
  :param samples: Total number of cases; defaults to one per cell (full coverage).
  :param seed: Base seed; the run is reproducible for a fixed active library set.
  :param libraries: Explicit library set to pin; ``None`` uses matplotlib + seaborn plus plotly when usable.
  :param strict_coverage: When the budget cannot cover every cell, error instead of warning and proceeding.
  :return: The generation summary (allocation, active libraries, image count, messages).
  :raises DatagenError: On an unsatisfiable library pin, or under-budget with ``strict_coverage``.
  """
  cells = build_cells()
  active, messages = resolve_libraries(libraries)
  budget = len(cells) if samples is None else samples
  allocation = allocate(budget, cells)
  messages = [*messages, *_coverage_messages(allocation, strict=strict_coverage)]

  images_dir = out_dir / IMAGES_DIRNAME
  images_dir.mkdir(parents=True, exist_ok=True)
  backends = {name: get_backend(name) for name in active}

  records: list[ManifestRecord] = []
  index = 0
  for cell_index, (cell, count) in enumerate(zip(allocation.cells, allocation.counts, strict=True)):
    for case_index in range(count):
      library = active[case_index % len(active)]
      case = build_case(cell, _case_rng(seed, cell_index, case_index))
      filename = f"{index:04d}-{cell.label}-{library}.png"
      backends[library].render(case.scene, images_dir / filename)
      records.append(
        ManifestRecord(image=f"{IMAGES_DIRNAME}/{filename}", library=library, labels=case.labels),
      )
      index += 1

  run = _RunInfo(seed=seed, samples=budget, libraries=active, requested=libraries, messages=messages)
  write_manifest(out_dir / MANIFEST_NAME, records)
  _write_config(out_dir / CONFIG_NAME)
  _write_meta(out_dir / META_NAME, allocation, run)
  return GenerationResult(
    out_dir=out_dir,
    allocation=allocation,
    libraries=tuple(active),
    image_count=len(records),
    messages=tuple(messages),
  )


def resolve_libraries(requested: list[str] | None) -> tuple[list[str], list[str]]:
  """Decide the active library set and any operator-facing messages.

  With no request, matplotlib and seaborn are always active and plotly joins them when usable, otherwise it drops with a
  logged message (graceful degradation). An explicit ``--libraries`` pin is honored exactly, and pinning plotly when its
  static export is unavailable is an error, not a silent drop (docs/adr/0013).

  :param requested: The explicit library set, or ``None`` for the default policy.
  :return: ``(active library names, messages)``.
  :raises DatagenError: If a requested library is unknown, or plotly is pinned but unusable.
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
    return active, []
  active = list(MANDATORY_LIBRARIES)
  if plotly_usable():
    active.append("plotly")
    return active, []
  message = f"plotly disabled: kaleido static export unavailable; rendering with {', '.join(MANDATORY_LIBRARIES)}"
  return active, [message]


def _coverage_messages(allocation: Allocation, *, strict: bool) -> list[str]:
  """Warn (or, under ``strict``, error) when the budget leaves cells uncovered."""
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


def _case_rng(seed: int, cell_index: int, case_index: int) -> random.Random:
  # String seed so the RNG is deterministic regardless of PYTHONHASHSEED (random.Random hashes str/bytes with sha512).
  # Pseudo-randomness is exactly what we want here (reproducible synthetic data), not cryptographic strength.
  return random.Random(f"{seed}:{cell_index}:{case_index}")  # noqa: S311 - reproducible test data, not security


@dataclass(frozen=True)
class _RunInfo:
  """The reproducibility inputs recorded in ``meta.json`` (bundled so the writer stays a two-argument helper)."""

  seed: int
  samples: int
  libraries: list[str]
  requested: list[str] | None
  messages: list[str]


def _write_config(path: Path) -> None:
  """Write the dataset's ``charr.toml`` so the checker is told the palette/font the charts were drawn against."""
  palette = json.dumps(canonical_palette())
  fonts = json.dumps(canonical_fonts())
  body = (
    "# Written by charr-datagen. This is the checker config the dataset was generated against;\n"
    "# charr-eval discovers it next to the manifest so the palette and font rules are judged\n"
    "# against the same expectations the charts were drawn for.\n"
    f"palette = {palette}\n"
    f"fonts = {fonts}\n"
  )
  path.write_text(body, encoding="ascii")


def _write_meta(path: Path, allocation: Allocation, run: "_RunInfo") -> None:
  """Write ``meta.json`` recording the run's reproducibility inputs and the realized allocation."""
  meta = {
    "charr_datagen_version": __version__,
    "charr_version": charr.__version__,
    "seed": run.seed,
    "samples": run.samples,
    "libraries": run.libraries,
    "libraries_requested": run.requested,
    "cells": [
      {"rule": cell.rule_id, "polarity": cell.polarity.value, "count": count}
      for cell, count in zip(allocation.cells, allocation.counts, strict=True)
    ],
    "uncovered": [cell.label for cell in allocation.uncovered],
    "min_samples_for_full_coverage": allocation.min_for_full_coverage,
    "messages": run.messages,
  }
  path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="ascii")
