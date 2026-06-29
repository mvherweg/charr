"""Tests for the style-config sampler: shape, distinctness, determinism, and cross-config variety (docs/adr/0019)."""

import random

import pytest
from charr_datagen.colour import T_WITHIN, delta_e2000, srgb_hex_to_lab
from charr_datagen.configs import (
  FONTS_MAX,
  FONTS_MIN,
  PALETTE_MAX,
  PALETTE_MIN,
  sample_config,
  sample_configs,
)
from charr_datagen.fonts import MAX_APPROVED


@pytest.mark.parametrize("seed", range(20))
def test_sampled_config_has_a_valid_palette_and_font_set(seed: int) -> None:
  config = sample_config("config-00", random.Random(seed))
  assert PALETTE_MIN <= config.palette_size <= PALETTE_MAX
  assert FONTS_MIN <= len(config.fonts) <= FONTS_MAX <= MAX_APPROVED
  # The palette colours are mutually distinct (the by-construction basis for palette compliance).
  labs = [srgb_hex_to_lab(colour) for colour in config.palette]
  for i, first in enumerate(labs):
    for second in labs[i + 1 :]:
      assert delta_e2000(first, second) >= T_WITHIN
  assert len(set(config.font_names())) == len(config.fonts)


def test_sample_configs_is_deterministic_for_a_fixed_seed() -> None:
  first = sample_configs(5, seed=7)
  second = sample_configs(5, seed=7)
  assert first == second
  assert [config.name for config in first] == ["config-00", "config-01", "config-02", "config-03", "config-04"]


def test_sample_configs_are_independent_across_the_run() -> None:
  # Independent sampling should yield varied palettes and font sets across a run (the anti-prior payoff). With eight
  # configs this is overwhelmingly likely; a single identical-everything run would signal a seeding bug.
  configs = sample_configs(8, seed=0)
  assert len({config.palette for config in configs}) > 1
  assert len({tuple(config.font_names()) for config in configs}) > 1


def test_sample_configs_rejects_a_non_positive_count() -> None:
  with pytest.raises(ValueError, match="at least one config"):
    sample_configs(0, seed=0)
