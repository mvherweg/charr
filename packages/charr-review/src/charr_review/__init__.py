"""Charr review.

A local single-page web app to browse a ``charr-eval`` run image-by-image: each chart alongside its per-rule expected
verdict, the model's predicted verdict, the recomputed confusion outcome, and the model's rationale (docs/adr/0022,
docs/adr/0023). It reads an existing substrate only -- no LLM calls.
"""

__version__ = "0.1.0"
