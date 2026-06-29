"""Tests for the font registry: property-derived distinctness, coverage, sampling, and faithful registration.

These are seed-robust (docs/adr/0021): distinctness and coverage are pure metadata inspection, and the sampling
guarantees are asserted by construction, not by a particular seed.
"""

import itertools
import random

import pytest
from charr_datagen import (
  rendering,  # noqa: F401 - importing rendering registers the bundled fonts (behaviour under test)
)
from charr_datagen.fonts import (
  MAX_APPROVED,
  SUPPORTED_FONTS,
  Font,
  are_distinct,
  font_path,
  sample_approved,
  sample_violation,
)
from matplotlib import font_manager


def test_supported_fonts_are_uniquely_named_and_filed() -> None:
  names = [font.name for font in SUPPORTED_FONTS]
  files = [font.file for font in SUPPORTED_FONTS]
  assert len(set(names)) == len(names)
  assert len(set(files)) == len(files)


def test_bundled_font_files_are_present() -> None:
  for font in SUPPORTED_FONTS:
    assert font_path(font).is_file(), f"missing bundled font file for {font.name}"


def test_buckets_outnumber_the_max_approved_set() -> None:
  # With more distinct buckets than the largest approved set, an approved selection can never occupy every bucket, so a
  # distinct violation font always exists - the coverage guarantee, as pure metadata.
  buckets = {font.bucket for font in SUPPORTED_FONTS}
  assert len(buckets) > MAX_APPROVED


def test_every_approved_subset_has_a_distinct_violation() -> None:
  for size in range(1, MAX_APPROVED + 1):
    for approved in itertools.combinations(SUPPORTED_FONTS, size):
      candidates = [font for font in SUPPORTED_FONTS if all(are_distinct(font, chosen) for chosen in approved)]
      assert candidates, f"no distinct violation for approved set {[f.name for f in approved]}"


def test_distinctness_is_false_within_a_bucket_and_true_across_buckets() -> None:
  sans = [font for font in SUPPORTED_FONTS if font.bucket == (False, False, False)]
  assert len(sans) >= 2, "expected sibling sans fonts to exercise within-bucket distinctness"
  assert not are_distinct(sans[0], sans[1])  # siblings: never a violation pair
  serif = next(font for font in SUPPORTED_FONTS if font.bucket == (True, False, False))
  assert are_distinct(sans[0], serif)


@pytest.mark.parametrize("size", [1, 2, 3])
def test_sample_approved_returns_distinct_fonts(size: int) -> None:
  for seed in range(20):
    approved = sample_approved(random.Random(seed), size)
    assert len(approved) == size
    assert len(set(approved)) == size
    assert all(isinstance(font, Font) for font in approved)


@pytest.mark.parametrize("size", [1, 2, 3])
def test_sampled_violation_differs_from_every_approved_font(size: int) -> None:
  for seed in range(50):
    rng = random.Random(seed)
    approved = sample_approved(rng, size)
    violation = sample_violation(rng, approved)
    assert all(are_distinct(violation, font) for font in approved)


def test_sample_approved_rejects_out_of_range_sizes() -> None:
  with pytest.raises(ValueError, match="between 1 and"):
    sample_approved(random.Random(0), 0)
  with pytest.raises(ValueError, match="between 1 and"):
    sample_approved(random.Random(0), MAX_APPROVED + 1)


def test_registration_resolves_every_font_to_its_own_family() -> None:
  # Importing rendering (top of file) registered the bundled fonts and would have raised on a silent fallback; here we
  # confirm each family resolves to itself - the no-fallback guarantee behind font-compliance ground truth.
  for font in SUPPORTED_FONTS:
    resolved = font_manager.findfont(font.name, fallback_to_default=False)
    assert font_manager.FontProperties(fname=resolved).get_name() == font.name
