"""The bundled font registry and property-derived distinctness (docs/adr/0021).

Fonts are the second half of a style-config: a config approves one to three of them, and a font-violation chart uses one
that is reliably distinguishable from every approved font. There is no clean perceptual metric for fonts, so
distinctness is *structural*: each font is tagged with distinguishing properties - serifed vs not, monospaced vs not,
script vs not - and two fonts are reliably distinct iff they differ on at least one. A *bucket* is a property tuple; the
supported set ships at least one font per bucket and may hold siblings within a bucket (e.g. a slab serif alongside a
serif) purely for compliant variety - siblings are never used as violations, because they are not guaranteed distinct.

The fonts are bundled in-repo (``fonts/*.ttf``) so rendering is reproducible across machines and licences stay clean
(OFL / Apache-2.0; see ``fonts/LICENSES``). This module is backend-agnostic data and sampling; the matplotlib
registration and the no-silent-fallback check live in :mod:`charr_datagen.rendering`.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

# A config approves between one and this many fonts (docs/adr/0019); the violation is drawn from outside that set.
MAX_APPROVED: int = 3


@dataclass(frozen=True)
class Font:
  """A bundled font, tagged with its distinguishing structural properties.

  :param name: The family name - used both as the matplotlib family and as the name written to the dataset's checker
    config, so the font rule is judged against the same family the chart was drawn with.
  :param file: The font file name under the bundled ``fonts/`` directory.
  :param serifs: Whether the typeface has serifs (a serif or slab-serif).
  :param monospaced: Whether the typeface is fixed-width.
  :param script: Whether the typeface is a script / handwriting / display face.
  """

  name: str
  file: str
  serifs: bool
  monospaced: bool
  script: bool

  @property
  def bucket(self) -> tuple[bool, bool, bool]:
    """Return the distinguishing-property tuple; fonts sharing a bucket are not reliably distinct.

    :return: ``(serifs, monospaced, script)``.
    """
    return (self.serifs, self.monospaced, self.script)


# The curated supported set: at least one font per distinguishing bucket, plus a sibling in the sans and serif buckets
# for compliant variety. All redistributable (OFL, except Roboto Slab which is Apache-2.0). The whimsical outlier is the
# script face (Caveat): in configs that approve it, handwriting is *compliant*, which strips the prior that handwriting
# is automatically wrong for a chart (docs/adr/0021).
SUPPORTED_FONTS: tuple[Font, ...] = (
  Font("Open Sans", "OpenSans-Regular.ttf", serifs=False, monospaced=False, script=False),
  Font("Montserrat", "Montserrat-Regular.ttf", serifs=False, monospaced=False, script=False),
  Font("Lora", "Lora-Regular.ttf", serifs=True, monospaced=False, script=False),
  Font("Roboto Slab", "RobotoSlab-Regular.ttf", serifs=True, monospaced=False, script=False),
  Font("JetBrains Mono", "JetBrainsMono-Regular.ttf", serifs=False, monospaced=True, script=False),
  Font("Caveat", "Caveat-Regular.ttf", serifs=False, monospaced=False, script=True),
)


def are_distinct(first: Font, second: Font) -> bool:
  """Report whether two fonts are reliably distinguishable.

  Distinctness is derived: two fonts differ reliably iff they differ on at least one distinguishing property (that is,
  they sit in different buckets). Same-bucket siblings return ``False`` and are therefore never used as violations.

  :param first: One font.
  :param second: The other font.
  :return: True if the two fonts differ on a distinguishing property.
  """
  return first.bucket != second.bucket


def sample_approved(rng: random.Random, size: int) -> tuple[Font, ...]:
  """Sample a config's approved font set: ``size`` distinct fonts from the supported set.

  Approved fonts may share a bucket (siblings) - that just adds compliant variety; the violation sampler still
  guarantees a distinct off-set font.

  :param rng: Seeded RNG owning all randomness.
  :param size: Number of fonts to approve; must be between 1 and :data:`MAX_APPROVED`.
  :return: The approved fonts.
  :raises ValueError: If ``size`` is out of range.
  """
  if not 1 <= size <= MAX_APPROVED:
    msg = f"approved font count must be between 1 and {MAX_APPROVED}, got {size}"
    raise ValueError(msg)
  return tuple(rng.sample(SUPPORTED_FONTS, size))


def sample_violation(rng: random.Random, approved: Sequence[Font]) -> Font:
  """Sample a font that differs by at least one distinguishing property from *every* approved font.

  The result is reliably distinguishable from all approved fonts, so a ``font-compliance: fail`` chart drawn with it is
  a true violation by construction.

  :param rng: Seeded RNG owning all randomness.
  :param approved: The config's approved fonts.
  :return: A supported font outside every approved bucket.
  :raises DatagenError: If no such font exists (impossible for the shipped set; a loud backstop on registry drift).
  """
  candidates = [font for font in SUPPORTED_FONTS if all(are_distinct(font, font_in) for font_in in approved)]
  if not candidates:
    from charr_datagen.errors import DatagenError  # noqa: PLC0415 - lazy import keeps this module backend/dep free.

    approved_names = ", ".join(font.name for font in approved)
    msg = f"no supported font is distinct from every approved font ({approved_names}); the registry lacks a free bucket"
    raise DatagenError(msg)
  return rng.choice(candidates)


def font_path(font: Font) -> Path:
  """Return the filesystem path to a bundled font file.

  :param font: The font whose ``.ttf`` to locate.
  :return: The path to the bundled font file.
  """
  return Path(str(resources.files("charr_datagen").joinpath("fonts", font.file)))
