"""The generator's error type, in its own module so low-level helpers can raise it without import cycles.

``DatagenError`` is a :class:`~charr.models.CharrError`, so the CLI catches it uniformly and maps it to the
"could not run" exit code. It lives here (rather than in :mod:`charr_datagen.generate`) because modules the orchestrator
depends on - such as :mod:`charr_datagen.colour` - need to raise it too, and importing it from ``generate`` would form a
cycle.
"""

from charr.models import CharrError


class DatagenError(CharrError):
  """Raised when a generation run cannot proceed (bad library pin, under-budget, or an exhausted sampler)."""
