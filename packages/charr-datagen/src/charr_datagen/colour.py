"""Perceptual colour sampling for style-configs: CIEDE2000 distance with bounded-retry rejection (docs/adr/0020).

A style-config needs a palette of mutually distinguishable colours and, per palette-violation chart, an off-palette
colour that is *unmistakably* outside the palette - so ``palette-compliance`` ground truth holds by construction
(docs/adr/0015). "Sufficiently different" is a perceptual question, so distances are measured with **CIEDE2000** in
CIELAB, not in RGB. The conversion and the ``deltaE2000`` formula are implemented inline (no colour-science dependency);
the formula is unit-tested against the Sharma et al. (2005) reference vectors so its correctness is verified, not
assumed.

Colours are sampled by bounded-retry rejection inside a white-legible band (a mid lightness and a minimum chroma, in
gamut), keeping each candidate that is far enough from those already chosen. A density estimate shows the band holds
far more distinct colours than any chart needs (at most 6 palette + 1 violation), so the retry cap is a loud backstop,
never a working limit.

The same deltaE2000 machinery serves the readability rules, which judge background/gridline-vs-mark contrast
irrespective of the palette: :func:`sample_far_from` keeps a colour clear of every plotted mark (a clean pass) and
:func:`sample_near` lands a colour within ``T_WITHIN`` of one (a blend), the two by-construction polarities of those
rules.
"""

import math
import random
from collections.abc import Sequence

type Lab = tuple[float, float, float]

# CIEDE2000 thresholds, calibrated as just-noticeable-difference multiples (deltaE2000 ~= 1 is the JND; 2-10 is
# "perceptible at a glance"). ``T_WITHIN`` keeps palette colours distinguishable as separate series; ``T_VIOLATION`` is
# distinctly larger so an off-palette colour is never borderline. Tunable; the property tests pin the guarantee.
T_WITHIN: float = 13.0
T_VIOLATION: float = 24.0  # calibrated down from ~26: at 26 the violation-vs-full-palette draw has a heavy retry tail.

# Defensive cap on rejection retries. The density of the legible band makes exhaustion implausible (see module docs);
# the cap exists so a future bad threshold/band fails loudly instead of looping forever.
DEFAULT_MAX_TRIES: int = 256

# White-legible band in CIELAB: a mid lightness so colours read on white, and a chroma floor so nothing samples as a
# near-grey. The upper chroma bound is generous; out-of-gamut draws are simply rejected and re-drawn.
_L_MIN, _L_MAX = 25.0, 75.0
_CHROMA_MIN, _CHROMA_MAX = 20.0, 75.0
_GAMUT_TRIES: int = 4096  # inner cap for "find one in-gamut band colour"; in-gamut draws are common, so this is slack.

# sRGB (IEC 61966-2-1) <-> CIE XYZ matrices, D65 reference white.
_RGB_TO_XYZ: tuple[tuple[float, float, float], ...] = (
  (0.4124564, 0.3575761, 0.1804375),
  (0.2126729, 0.7151522, 0.0721750),
  (0.0193339, 0.1191920, 0.9503041),
)
_XYZ_TO_RGB: tuple[tuple[float, float, float], ...] = (
  (3.2404542, -1.5371385, -0.4985314),
  (-0.9692660, 1.8760108, 0.0415560),
  (0.0556434, -0.2040259, 1.0572252),
)
_WHITE_D65: Lab = (0.95047, 1.0, 1.08883)
_DELTA = 6.0 / 29.0  # CIELAB f() break point.

# sRGB transfer-function break points (IEC 61966-2-1) and a small tolerance for the gamut test.
_SRGB_LINEAR_BREAK = 0.04045
_LINEAR_SRGB_BREAK = 0.0031308
_GAMUT_EPS = 1e-6

# Hue arithmetic is in degrees; these name the half- and full-circle wrap points.
_HALF_TURN = 180.0
_FULL_TURN = 360.0


def delta_e2000(lab1: Lab, lab2: Lab) -> float:
  """Return the CIEDE2000 colour difference between two CIELAB colours.

  Implements the standard formula (with unit parametric weights ``kL = kC = kH = 1``); verified against the Sharma et
  al. (2005) reference vectors in the tests.

  :param lab1: The first colour as ``(L*, a*, b*)``.
  :param lab2: The second colour as ``(L*, a*, b*)``.
  :return: The ``deltaE2000`` difference (0 is identical; ~1 is a just-noticeable difference).
  """
  l1, a1, b1 = lab1
  l2, a2, b2 = lab2
  c1 = math.hypot(a1, b1)
  c2 = math.hypot(a2, b2)
  c_bar = (c1 + c2) / 2.0
  g = 0.5 * (1.0 - math.sqrt(c_bar**7 / (c_bar**7 + 25.0**7))) if c_bar > 0 else 0.0
  a1p, a2p = (1.0 + g) * a1, (1.0 + g) * a2
  c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
  h1p, h2p = _hue_degrees(b1, a1p), _hue_degrees(b2, a2p)

  d_lp = l2 - l1
  d_cp = c2p - c1p
  d_hp = _delta_hue(c1p, c2p, h1p, h2p)
  d_big_hp = 2.0 * math.sqrt(c1p * c2p) * math.sin(math.radians(d_hp / 2.0))

  l_bar = (l1 + l2) / 2.0
  c_bar_p = (c1p + c2p) / 2.0
  h_bar_p = _mean_hue(c1p, c2p, h1p, h2p)
  t = (
    1.0
    - 0.17 * math.cos(math.radians(h_bar_p - 30.0))
    + 0.24 * math.cos(math.radians(2.0 * h_bar_p))
    + 0.32 * math.cos(math.radians(3.0 * h_bar_p + 6.0))
    - 0.20 * math.cos(math.radians(4.0 * h_bar_p - 63.0))
  )
  s_l = 1.0 + (0.015 * (l_bar - 50.0) ** 2) / math.sqrt(20.0 + (l_bar - 50.0) ** 2)
  s_c = 1.0 + 0.045 * c_bar_p
  s_h = 1.0 + 0.015 * c_bar_p * t
  d_theta = 30.0 * math.exp(-(((h_bar_p - 275.0) / 25.0) ** 2))
  r_c = 2.0 * math.sqrt(c_bar_p**7 / (c_bar_p**7 + 25.0**7)) if c_bar_p > 0 else 0.0
  r_t = -math.sin(math.radians(2.0 * d_theta)) * r_c
  return math.sqrt(
    (d_lp / s_l) ** 2 + (d_cp / s_c) ** 2 + (d_big_hp / s_h) ** 2 + r_t * (d_cp / s_c) * (d_big_hp / s_h)
  )


def srgb_hex_to_lab(colour: str) -> Lab:
  """Convert an sRGB hex string to CIELAB (D65).

  :param colour: An sRGB colour as ``#rrggbb`` (the leading ``#`` is optional).
  :return: The colour as ``(L*, a*, b*)``.
  """
  raw = colour.lstrip("#")
  r, g, b = (int(raw[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
  return _linear_rgb_to_lab(_srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b))


def sample_palette(
  rng: random.Random, size: int, *, min_distance: float = T_WITHIN, max_tries: int = DEFAULT_MAX_TRIES
) -> list[str]:
  """Sample ``size`` legible sRGB colours that are mutually at least ``min_distance`` apart in CIEDE2000.

  :param rng: Seeded RNG owning all randomness.
  :param size: Number of colours to draw (the palette size).
  :param min_distance: Minimum pairwise ``deltaE2000`` between palette colours.
  :param max_tries: Retry budget per colour before giving up (a loud backstop, not a working limit).
  :return: The palette as ``#rrggbb`` strings.
  :raises ValueError: If ``size`` is negative.
  :raises DatagenError: If a colour cannot be placed within ``max_tries`` (a misconfigured threshold or band).
  """
  if size < 0:
    msg = f"palette size must be non-negative, got {size}"
    raise ValueError(msg)
  chosen: list[tuple[str, Lab]] = []
  for _ in range(size):
    chosen.append(_draw_far_from(rng, [lab for _, lab in chosen], min_distance, max_tries))
  return [hex_value for hex_value, _ in chosen]


def sample_far_from(
  rng: random.Random, colours: Sequence[str], *, min_distance: float = T_VIOLATION, max_tries: int = DEFAULT_MAX_TRIES
) -> str:
  """Sample one legible sRGB colour at least ``min_distance`` (deltaE2000) from every colour in ``colours``.

  The general "keep clear of these" primitive: used both for an off-palette violation colour and for a background or
  gridline that must stay clearly distinct from every plotted mark (the readability rules judge that perceptual
  distance, irrespective of the palette).

  :param rng: Seeded RNG owning all randomness.
  :param colours: The colours to stay clear of, as ``#rrggbb`` strings.
  :param min_distance: Minimum ``deltaE2000`` from every colour in ``colours``.
  :param max_tries: Retry budget before giving up (a loud backstop, not a working limit).
  :return: The sampled colour as ``#rrggbb``.
  :raises DatagenError: If no colour can be placed within ``max_tries``.
  """
  hex_value, _ = _draw_far_from(rng, [srgb_hex_to_lab(colour) for colour in colours], min_distance, max_tries)
  return hex_value


def sample_near(
  rng: random.Random, target: str, *, max_distance: float = T_WITHIN, max_tries: int = DEFAULT_MAX_TRIES
) -> str:
  """Sample one in-gamut sRGB colour within ``max_distance`` (deltaE2000) of ``target`` - a near-match that blends.

  Used to make a background or gridline too close to a plotted mark: within ``T_WITHIN`` the two are not reliably
  distinguishable. The result may be any in-gamut colour (it is not constrained to the palette or the legible band);
  only its closeness to ``target`` matters. Sampled by perturbing ``target`` in CIELAB so the success rate stays high
  (rejection from the whole gamut would rarely land in so small a ball), then verified in deltaE2000.

  :param rng: Seeded RNG owning all randomness.
  :param target: The colour to land near, as ``#rrggbb``.
  :param max_distance: Maximum ``deltaE2000`` from ``target``.
  :param max_tries: Retry budget before giving up (a loud backstop, not a working limit).
  :return: The near colour as ``#rrggbb``.
  :raises DatagenError: If no colour can be placed within ``max_tries``.
  """
  target_lab = srgb_hex_to_lab(target)
  for _ in range(max_tries):
    candidate = _perturb_in_gamut(rng, target_lab, max_distance)
    if candidate is not None and delta_e2000(srgb_hex_to_lab(candidate), target_lab) <= max_distance:
      return candidate
  from charr_datagen.errors import DatagenError  # noqa: PLC0415 - lazy import avoids a colour<->generate import cycle.

  msg = f"could not sample a colour within deltaE2000 <= {max_distance} of {target!r} within {max_tries} tries"
  raise DatagenError(msg)


def sample_off_palette(
  rng: random.Random, palette: Sequence[str], *, min_distance: float = T_VIOLATION, max_tries: int = DEFAULT_MAX_TRIES
) -> str:
  """Sample one legible sRGB colour clearly outside ``palette`` (the palette-compliance violation colour).

  A named use of :func:`sample_far_from`: the result is at least ``min_distance`` from every palette colour.

  :param rng: Seeded RNG owning all randomness.
  :param palette: The approved palette as ``#rrggbb`` strings; the result is clearly outside it.
  :param min_distance: Minimum ``deltaE2000`` from every palette colour.
  :param max_tries: Retry budget before giving up (a loud backstop, not a working limit).
  :return: The off-palette colour as ``#rrggbb``.
  :raises DatagenError: If no colour can be placed within ``max_tries``.
  """
  return sample_far_from(rng, palette, min_distance=min_distance, max_tries=max_tries)


def _draw_far_from(rng: random.Random, labs: list[Lab], min_distance: float, max_tries: int) -> tuple[str, Lab]:
  """Draw a legible colour whose CIEDE2000 distance to every colour in ``labs`` is at least ``min_distance``."""
  for _ in range(max_tries):
    hex_value, lab = _random_legible_colour(rng)
    if all(delta_e2000(lab, other) >= min_distance for other in labs):
      return hex_value, lab
  from charr_datagen.errors import DatagenError  # noqa: PLC0415 - lazy import avoids a colour<->generate import cycle.

  msg = (
    f"could not sample a colour at deltaE2000 >= {min_distance} within {max_tries} tries "
    f"({len(labs)} colours already placed); the threshold or legible band is too tight"
  )
  raise DatagenError(msg)


def _perturb_in_gamut(rng: random.Random, lab: Lab, radius: float) -> str | None:
  """Offset ``lab`` by a random vector of CIELAB length <= ``radius`` and return the sRGB hex, or None if out of gamut.

  The offset is uniform within a ball: a random direction times ``radius * u ** (1/3)``. CIELAB length is a deltaE76
  proxy, which is an upper bound on deltaE2000 in this region, so the caller's deltaE2000 check almost always accepts.
  """
  dx, dy, dz = rng.gauss(0.0, 1.0), rng.gauss(0.0, 1.0), rng.gauss(0.0, 1.0)
  norm = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
  scale = radius * (rng.random() ** (1.0 / 3.0)) / norm
  lightness, a, b = lab
  return _lab_to_srgb_hex((lightness + dx * scale, a + dy * scale, b + dz * scale))


def _random_legible_colour(rng: random.Random) -> tuple[str, Lab]:
  """Return a random in-gamut colour from the white-legible band, as ``(hex, lab-of-the-rendered-hex)``."""
  for _ in range(_GAMUT_TRIES):
    lightness = rng.uniform(_L_MIN, _L_MAX)
    chroma = rng.uniform(_CHROMA_MIN, _CHROMA_MAX)
    hue = rng.uniform(0.0, 2.0 * math.pi)
    lab = (lightness, chroma * math.cos(hue), chroma * math.sin(hue))
    hex_value = _lab_to_srgb_hex(lab)
    if hex_value is not None:
      # Use the lab of the actually-rendered (8-bit-quantized) hex, so distances reflect what gets drawn.
      return hex_value, srgb_hex_to_lab(hex_value)
  msg = "exhausted gamut search for a legible colour; the band is misconfigured"
  raise AssertionError(msg)


def _lab_to_srgb_hex(lab: Lab) -> str | None:
  """Convert CIELAB to an sRGB hex string, or ``None`` when the colour falls outside the sRGB gamut."""
  lightness, a, b = lab
  fy = (lightness + 16.0) / 116.0
  fx, fz = fy + a / 500.0, fy - b / 200.0
  xyz = (_WHITE_D65[i] * _f_inverse(f) for i, f in enumerate((fx, fy, fz)))
  x, y, z = xyz
  linear = [row[0] * x + row[1] * y + row[2] * z for row in _XYZ_TO_RGB]
  channels: list[int] = []
  for value in linear:
    srgb = _linear_to_srgb(value)
    if srgb < -_GAMUT_EPS or srgb > 1.0 + _GAMUT_EPS:
      return None
    channels.append(round(min(1.0, max(0.0, srgb)) * 255.0))
  return "#{:02x}{:02x}{:02x}".format(*channels)


def _linear_rgb_to_lab(r: float, g: float, b: float) -> Lab:
  x, y, z = (row[0] * r + row[1] * g + row[2] * b for row in _RGB_TO_XYZ)
  fx, fy, fz = (_f_forward(value / white) for value, white in zip((x, y, z), _WHITE_D65, strict=True))
  return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def _f_forward(t: float) -> float:
  return t ** (1.0 / 3.0) if t > _DELTA**3 else t / (3.0 * _DELTA**2) + 4.0 / 29.0


def _f_inverse(t: float) -> float:
  return t**3 if t > _DELTA else 3.0 * _DELTA**2 * (t - 4.0 / 29.0)


def _srgb_to_linear(c: float) -> float:
  return c / 12.92 if c <= _SRGB_LINEAR_BREAK else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
  return 12.92 * c if c <= _LINEAR_SRGB_BREAK else 1.055 * c ** (1.0 / 2.4) - 0.055


def _hue_degrees(b: float, a_prime: float) -> float:
  if a_prime == 0.0 and b == 0.0:
    return 0.0
  return math.degrees(math.atan2(b, a_prime)) % 360.0


def _delta_hue(c1p: float, c2p: float, h1p: float, h2p: float) -> float:
  if c1p * c2p == 0.0:
    return 0.0
  diff = h2p - h1p
  if abs(diff) <= _HALF_TURN:
    return diff
  return diff - _FULL_TURN if h2p > h1p else diff + _FULL_TURN


def _mean_hue(c1p: float, c2p: float, h1p: float, h2p: float) -> float:
  if c1p * c2p == 0.0:
    return h1p + h2p
  if abs(h1p - h2p) <= _HALF_TURN:
    return (h1p + h2p) / 2.0
  if h1p + h2p < _FULL_TURN:
    return (h1p + h2p + _FULL_TURN) / 2.0
  return (h1p + h2p - _FULL_TURN) / 2.0
