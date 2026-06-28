"""Tests for the in-code domain registry: enough vocabulary, unique names, and the expected first cut."""

import pytest
from charr_datagen.domains import DOMAINS, Domain

_MIN_CATEGORIES = 6
_MIN_SERIES = 2
_EXPECTED_DOMAIN_COUNT = 8


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda domain: domain.name)
def test_domain_carries_enough_ascii_vocabulary(domain: Domain) -> None:
  assert len(domain.categories) >= _MIN_CATEGORIES  # recipes sample up to five categories
  assert len(domain.series_names) >= _MIN_SERIES  # a multi-group chart picks two to three series
  low, high = domain.value_range
  assert low < high
  text = (domain.name, domain.category_axis_label, domain.quantity, domain.unit, *domain.titles, *domain.categories)
  assert all(piece.isascii() for piece in text)


def test_domain_names_are_unique() -> None:
  names = [domain.name for domain in DOMAINS]
  assert len(set(names)) == len(names)


def test_first_cut_ships_eight_domains_including_the_whimsical_pair() -> None:
  assert len(DOMAINS) == _EXPECTED_DOMAIN_COUNT
  names = {domain.name for domain in DOMAINS}
  assert {"improbable", "mundane-absurd"} <= names
