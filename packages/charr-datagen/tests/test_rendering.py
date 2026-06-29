"""Tests for the value-label layout: the no-overlapping-elements contrast is layout-only and leak-free.

Pixels are out of scope (docs/adr/0014); these assert the shared layout that both backends consume - that both
polarities draw the same real values and differ only in placement, so neither the presence nor the content of the
labels can leak the verdict (which would let a model pass by reading rather than seeing).
"""

import random

import pytest
from charr.models import Verdict
from charr_datagen.cells import Cell
from charr_datagen.configs import sample_config
from charr_datagen.recipes import REGISTRY, assemble
from charr_datagen.rendering import _data_label_layout
from charr_datagen.scenes import ChartScene

_KINDS = ("bar", "line", "scatter", "pie")


def _overlap_scene(name: str, polarity: Verdict) -> ChartScene:
  config = sample_config("config-00", random.Random(0))
  chart_type = next(chart_type for chart_type in REGISTRY if chart_type.name == name)
  return assemble(Cell("no-overlapping-elements", polarity), chart_type, config, random.Random(1)).scene


@pytest.mark.parametrize("name", _KINDS)
def test_both_polarities_label_the_same_real_values_and_differ_only_in_layout(name: str) -> None:
  fail = _overlap_scene(name, Verdict.FAIL)
  passing = _overlap_scene(name, Verdict.PASS)  # same seed and config -> identical data
  fail_anchors, _ = _data_label_layout(fail)
  pass_anchors, _ = _data_label_layout(passing)
  expected = [f"{value:g}" for value in fail.series[0].y[:5]]
  assert [text for _, _, text in fail_anchors] == expected
  assert [text for _, _, text in pass_anchors] == expected  # content and count are symmetric across the contrast
  # The only signal is placement: colliding piles every label at one x; separated spreads them across distinct x.
  assert len({x for x, _, _ in fail_anchors}) == 1
  assert len({round(x, 3) for x, _, _ in pass_anchors}) == len(pass_anchors)


@pytest.mark.parametrize("name", _KINDS)
@pytest.mark.parametrize("polarity", [Verdict.PASS, Verdict.FAIL])
def test_no_label_text_names_the_verdict(name: str, polarity: Verdict) -> None:
  # Guards against re-introducing answer-leaking text (the retired "...collides" sentence): every label is a number.
  anchors, _ = _data_label_layout(_overlap_scene(name, polarity))
  for _, _, text in anchors:
    assert text.lstrip("-").replace(".", "").isdigit(), f"non-numeric value label {text!r} could leak the verdict"
