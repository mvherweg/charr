"""Tests for the colour module: CIEDE2000 correctness (Sharma vectors), the sampler guarantees, and termination.

These are seed-robust by design (docs/adr/0020): the distance check is verified against published reference data, and
the sampler is asserted to satisfy its distance guarantees and to terminate with a large retry margin.
"""

import random

import pytest
from charr_datagen.colour import (
  DEFAULT_MAX_TRIES,
  T_VIOLATION,
  T_WITHIN,
  delta_e2000,
  sample_far_from,
  sample_near,
  sample_off_palette,
  sample_palette,
  srgb_hex_to_lab,
)
from charr_datagen.errors import DatagenError

# A representative subset of the Sharma, Wu & Dalal (2005) CIEDE2000 reference vectors:
# (L1, a1, b1), (L2, a2, b2), expected deltaE2000. Chosen to exercise the hue-rotation term (blues), the achromatic
# path, the large-difference regime, and small near-grey differences.
_SHARMA_VECTORS: tuple[tuple[tuple[float, float, float], tuple[float, float, float], float], ...] = (
  ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
  ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
  ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
  ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
  ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0009), 7.1792),
  ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
  ((50.0000, 2.5000, 0.0000), (56.0000, -27.0000, -3.0000), 31.9030),
  ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
  ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
  ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
  ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
  ((6.7747, -0.2908, -2.4247), (5.8714, -0.0985, -2.2286), 0.6377),
)


@pytest.mark.parametrize(("lab1", "lab2", "expected"), _SHARMA_VECTORS)
def test_delta_e2000_matches_sharma_reference_vectors(
  lab1: tuple[float, float, float], lab2: tuple[float, float, float], expected: float
) -> None:
  assert delta_e2000(lab1, lab2) == pytest.approx(expected, abs=1e-3)


def test_delta_e2000_is_symmetric_and_zero_on_identity() -> None:
  lab1 = (40.0, 12.0, -30.0)
  lab2 = (55.0, -8.0, 22.0)
  assert delta_e2000(lab1, lab1) == pytest.approx(0.0, abs=1e-9)
  assert delta_e2000(lab1, lab2) == pytest.approx(delta_e2000(lab2, lab1), abs=1e-9)


def test_srgb_hex_round_trips_to_known_lab() -> None:
  # Pure white and pure black are exact reference points.
  assert srgb_hex_to_lab("#ffffff") == pytest.approx((100.0, 0.0, 0.0), abs=1e-2)
  assert srgb_hex_to_lab("#000000") == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)


@pytest.mark.parametrize("size", [1, 2, 3, 4, 5, 6])
def test_sampled_palette_colours_are_mutually_separated(size: int) -> None:
  for seed in range(20):
    palette = sample_palette(random.Random(seed), size)
    assert len(palette) == size
    labs = [srgb_hex_to_lab(colour) for colour in palette]
    for i, first in enumerate(labs):
      for second in labs[i + 1 :]:
        assert delta_e2000(first, second) >= T_WITHIN


@pytest.mark.parametrize("size", [1, 3, 6])
def test_off_palette_colour_is_far_from_every_palette_colour(size: int) -> None:
  for seed in range(20):
    rng = random.Random(seed)
    palette = sample_palette(rng, size)
    violation = srgb_hex_to_lab(sample_off_palette(rng, palette))
    for colour in palette:
      assert delta_e2000(violation, srgb_hex_to_lab(colour)) >= T_VIOLATION


@pytest.mark.parametrize("size", [1, 3, 6])
def test_sample_far_from_clears_every_given_colour(size: int) -> None:
  # The general "keep clear of these" primitive the readability rules use for a clean-pass background/gridline.
  for seed in range(20):
    rng = random.Random(seed)
    colours = sample_palette(rng, size)
    far = srgb_hex_to_lab(sample_far_from(rng, colours))
    for colour in colours:
      assert delta_e2000(far, srgb_hex_to_lab(colour)) >= T_VIOLATION


def test_sample_near_lands_within_the_blend_band_of_the_target() -> None:
  # The "blend" primitive: a background/gridline this close to a mark is not reliably distinguishable from it. Run many
  # seeds because the perturbation sampler must succeed reliably, not just on average.
  for seed in range(50):
    rng = random.Random(seed)
    target = sample_palette(rng, 1)[0]
    near = sample_near(rng, target)
    assert delta_e2000(srgb_hex_to_lab(near), srgb_hex_to_lab(target)) <= T_WITHIN


def test_sampling_terminates_with_a_wide_retry_margin() -> None:
  # The real cap is DEFAULT_MAX_TRIES (256); succeeding across many seeds at half that budget, with the largest palette
  # plus a violation (the tightest case), proves the density margin (docs/adr/0020). A regression that tightened the
  # threshold or band - pushing the retry tail up - would raise here well before users hit the real cap.
  budget = DEFAULT_MAX_TRIES // 2
  for seed in range(200):
    rng = random.Random(seed)
    palette = sample_palette(rng, 6, max_tries=budget)
    sample_off_palette(rng, palette, max_tries=budget)


def test_sampling_raises_a_clear_error_when_the_constraint_is_unsatisfiable() -> None:
  rng = random.Random(0)
  # An absurd within-distance no legible pair can satisfy forces exhaustion - the loud backstop.
  with pytest.raises(DatagenError, match="could not sample a colour"):
    sample_palette(rng, 6, min_distance=500.0, max_tries=16)
