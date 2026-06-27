"""Tests for the built-in rule catalog and selection logic."""

import pytest
from charr.rules import BUILTIN_RULES, BUILTIN_RULES_BY_ID, select_enabled_rules


def test_every_builtin_rule_has_a_unique_kebab_case_id() -> None:
  ids = [rule.id for rule in BUILTIN_RULES]
  assert len(ids) == len(set(ids))
  assert set(ids) == set(BUILTIN_RULES_BY_ID)
  assert all(rule_id == rule_id.lower() and " " not in rule_id for rule_id in ids)


def test_select_enabled_rules_returns_all_defaults_when_there_are_no_overrides() -> None:
  selected = select_enabled_rules([], [])
  assert [rule.id for rule in selected] == [rule.id for rule in BUILTIN_RULES if rule.enabled_by_default]


def test_select_enabled_rules_treats_a_non_empty_enable_as_an_allow_list() -> None:
  selected = select_enabled_rules(["has-title", "axes-labeled"], [])
  assert [rule.id for rule in selected] == ["has-title", "axes-labeled"]


def test_select_enabled_rules_lets_disable_win_over_enable() -> None:
  selected = select_enabled_rules(["has-title", "axes-labeled"], ["has-title"])
  assert [rule.id for rule in selected] == ["axes-labeled"]


def test_select_enabled_rules_preserves_catalog_order_regardless_of_enable_order() -> None:
  selected = select_enabled_rules(["axes-labeled", "has-title"], [])
  assert [rule.id for rule in selected] == ["has-title", "axes-labeled"]


def test_select_enabled_rules_raises_on_an_unknown_rule_id() -> None:
  with pytest.raises(KeyError):
    select_enabled_rules(["no-such-rule"], [])
