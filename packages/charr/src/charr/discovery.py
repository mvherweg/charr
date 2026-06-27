"""Turn raw CLI inputs (file paths, globs, directories) into a deterministic list of image files.

Expansion is intentionally minimal for the first increment: directories are scanned non-recursively and ``**`` is not
special. Results are de-duplicated in first-seen order and sorted within each input's expansion so the JSON report is
stable. An input that matches no image is a hard error, so typos and empty folders fail loudly.
"""

import glob
from collections.abc import Sequence
from pathlib import Path

from charr.models import IMAGE_SUFFIXES, CharrError


class DiscoveryError(CharrError):
  """Raised when an input matches no image file or names a non-image file directly."""


def discover_images(inputs: Sequence[str], *, cwd: Path) -> list[Path]:
  """Expand ``inputs`` into an ordered, de-duplicated list of existing image files.

  :param inputs: File paths, globs, or directories to expand.
  :param cwd: Directory that relative inputs and globs are resolved against.
  :return: Matching image files as absolute paths, de-duplicated in first-seen order.
  :raises DiscoveryError: If an input matches no image, or names a non-image file directly.
  """
  ordered: list[Path] = []
  seen: set[Path] = set()
  for raw in inputs:
    for path in _expand_input(raw, cwd):
      resolved = path.resolve()
      if resolved not in seen:
        seen.add(resolved)
        ordered.append(resolved)
  return ordered


def _expand_input(raw: str, cwd: Path) -> list[Path]:
  full = Path(raw) if Path(raw).is_absolute() else cwd / raw
  if full.is_dir():
    found = _images_in_directory(full)
    if not found:
      msg = f"no image files in directory: {raw}"
      raise DiscoveryError(msg)
    return found
  if glob.has_magic(raw):
    found = _expand_glob(raw, cwd)
    if not found:
      msg = f"glob matched no image files: {raw}"
      raise DiscoveryError(msg)
    return found
  if full.is_file():
    if not _is_image(full):
      expected = "/".join(sorted(IMAGE_SUFFIXES))
      msg = f"not an image file (expected {expected}): {raw}"
      raise DiscoveryError(msg)
    return [full]
  msg = f"input matched nothing: {raw}"
  raise DiscoveryError(msg)


def _expand_glob(raw: str, cwd: Path) -> list[Path]:
  if Path(raw).is_absolute():
    hits = [Path(match) for match in glob.glob(raw)]  # noqa: PTH207 - pathlib has no root_dir-relative glob
  else:
    hits = [cwd / match for match in glob.glob(raw, root_dir=cwd)]  # noqa: PTH207 - pathlib has no root_dir-relative glob
  return sorted(hit for hit in hits if hit.is_file() and _is_image(hit))


def _images_in_directory(directory: Path) -> list[Path]:
  return sorted(child for child in directory.iterdir() if child.is_file() and _is_image(child))


def _is_image(path: Path) -> bool:
  return path.suffix.lower() in IMAGE_SUFFIXES
