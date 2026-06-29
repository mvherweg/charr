"""Style-configs: independently sampled ``(palette, approved-fonts)`` expectations, one per dataset (docs/adr/0019).

A run sweeps across N style-configs, each written as its own self-describing dataset. A config is *sampled*, not
curated: a palette of mutually distinct colours (docs/adr/0020) and an approved font set (docs/adr/0021), drawn
independently and seeded from the base seed, so any palette can co-occur with any font set and there is no privileged
house style. Across a run a concrete colour or font is compliant in one config and a violation in another, which is what
removes the absolute-style prior the sweep exists to defeat.

The palette holds at least three colours so every chart type can colour its series or pie slices distinctly from the
palette (pies use three to five slices); the recipes bound the element count by the palette size.
"""

import random
from dataclasses import dataclass

from charr_datagen.colour import sample_palette
from charr_datagen.fonts import MAX_APPROVED, Font, sample_approved

# A palette holds 3-6 colours (3 is the floor so a pie's slices and a multi-group chart's series each get a distinct
# palette colour); a config approves 1 to MAX_APPROVED fonts.
PALETTE_MIN, PALETTE_MAX = 3, 6
FONTS_MIN, FONTS_MAX = 1, MAX_APPROVED


@dataclass(frozen=True)
class StyleConfig:
  """One sampled style expectation: the palette and approved fonts a dataset's charts are drawn against.

  :param name: The config's directory name within the run (e.g. ``config-00``).
  :param palette: The approved palette as ``#rrggbb`` colours; compliant charts draw only from it.
  :param fonts: The approved fonts; compliant charts use one of them.
  """

  name: str
  palette: tuple[str, ...]
  fonts: tuple[Font, ...]

  @property
  def palette_size(self) -> int:
    """Return the number of approved colours (the cap on distinctly-coloured chart elements).

    :return: The palette length.
    """
    return len(self.palette)

  def font_names(self) -> list[str]:
    """Return the approved font family names, for the dataset's checker config.

    :return: The approved fonts' family names, in order.
    """
    return [font.name for font in self.fonts]


def sample_config(name: str, rng: random.Random) -> StyleConfig:
  """Sample one style-config: an independently drawn palette and approved-font set.

  :param name: The config's directory name within the run.
  :param rng: A seeded RNG owned by this config.
  :return: The sampled style-config.
  """
  palette = tuple(sample_palette(rng, rng.randint(PALETTE_MIN, PALETTE_MAX)))
  fonts = sample_approved(rng, rng.randint(FONTS_MIN, FONTS_MAX))
  return StyleConfig(name=name, palette=palette, fonts=fonts)


def sample_configs(count: int, seed: int) -> list[StyleConfig]:
  """Sample ``count`` independent style-configs deterministically from a base seed.

  Each config is named ``config-NN`` and seeded from ``(seed, index)``, so a run is reproducible and two configs in the
  same run are independent.

  :param count: Number of style-configs to sample; must be positive.
  :param seed: The run's base seed.
  :return: The sampled configs, in index order.
  :raises ValueError: If ``count`` is not positive.
  """
  if count < 1:
    msg = f"a run needs at least one config, got {count}"
    raise ValueError(msg)
  # String seed so the stream is independent of PYTHONHASHSEED, matching the per-case seeding in generate.
  return [sample_config(f"config-{index:02d}", random.Random(f"{seed}:config:{index}")) for index in range(count)]  # noqa: S311 - reproducible synthetic data, not security
