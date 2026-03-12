"""Assign aggregated items to newsletter sections based on config rules."""

from __future__ import annotations

import logging
import re
from typing import Any

from src.utils.config_loader import load_newsletter_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rule matchers
# ---------------------------------------------------------------------------

def _field_value(item: dict[str, Any], field: str) -> Any:
    """Return the value of *field* on *item*, or ``None`` if absent."""
    return item.get(field)


def _match_pattern(value: Any, pattern: str) -> bool:
    """Return whether *value* matches the regex *pattern*."""
    if value is None:
        return False
    if isinstance(value, list):
        return any(
            bool(re.search(pattern, str(v))) for v in value
        )
    return bool(re.search(pattern, str(value)))


def _match_contains(value: Any, substring: str) -> bool:
    """Return whether *substring* appears in *value*.

    If *value* is a list, checks membership.  If it is a string, checks
    substring presence.
    """
    if value is None:
        return False
    if isinstance(value, list):
        return substring in value
    return substring in str(value)


def _match_contains_any(value: Any, candidates: list[str]) -> bool:
    """Return whether any of *candidates* appears in *value*."""
    if value is None or not candidates:
        return False
    return any(_match_contains(value, c) for c in candidates)


def _match_equals(value: Any, target: str) -> bool:
    """Return whether *value* exactly equals *target*."""
    if value is None:
        return False
    if isinstance(value, list):
        return target in value
    return str(value) == target


def _rule_matches(rule: dict[str, Any], item: dict[str, Any]) -> bool:
    """Evaluate a single rule dict against an *item*.

    A rule matches if **all** of its conditions are satisfied.  Supported
    conditions:

    * ``catch_all: true`` -- always matches.
    * ``field`` + ``pattern`` -- regex search on the field value.
    * ``field`` + ``contains`` -- substring / membership check.
    * ``field`` + ``contains_any`` -- any-of membership check.
    * ``field`` + ``equals`` -- exact equality.
    * ``type`` -- matches ``item["source_type"]`` or ``item["type"]``.

    If multiple condition keys appear in one rule they are combined with AND.
    """
    if rule.get("catch_all"):
        return True

    # ``type`` is a shortcut for matching the item type.
    if "type" in rule:
        item_type = item.get("source_type") or item.get("type")
        if str(item_type) != str(rule["type"]):
            return False

    field = rule.get("field")
    if field is None:
        # No field-based condition and no catch_all -- only ``type`` may
        # have been checked above.  If we got here, ``type`` matched (or
        # wasn't specified), so the rule matches.
        return True

    value = _field_value(item, field)

    if "pattern" in rule:
        if not _match_pattern(value, rule["pattern"]):
            return False
    if "contains" in rule:
        if not _match_contains(value, rule["contains"]):
            return False
    if "contains_any" in rule:
        if not _match_contains_any(value, rule["contains_any"]):
            return False
    if "equals" in rule:
        if not _match_equals(value, rule["equals"]):
            return False

    return True


def _section_matches(section: dict[str, Any], item: dict[str, Any]) -> bool:
    """Return whether *item* matches **any** rule in *section*.

    Each rule within a section's ``rules`` list is treated as an OR: if any
    single rule matches the item, the section matches.
    """
    rules = section.get("rules", [])
    if not rules:
        return False
    return any(_rule_matches(rule, item) for rule in rules)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def categorize(
    items: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Assign *items* to newsletter sections.

    Parameters
    ----------
    items:
        Aggregated, deduplicated items (e.g. from
        :func:`src.processor.aggregator.aggregate_month`).
    config:
        A newsletter config dict (as returned by
        :func:`src.utils.config_loader.load_newsletter_config`).  If
        *None*, the config is loaded automatically.

    Returns
    -------
    dict[str, list[dict]]
        Mapping of ``section_id`` to the items that belong to it.  Sections
        are evaluated in priority order (lowest number first) and each item
        is placed in the **first** matching section only.
    """
    if config is None:
        config = load_newsletter_config()

    sections = config.get("sections", [])
    # Sort by priority (lowest number = highest priority).
    sections_sorted = sorted(sections, key=lambda s: s.get("priority", 999))

    # Initialise the result with empty lists so every section is present.
    result: dict[str, list[dict[str, Any]]] = {
        s["id"]: [] for s in sections_sorted
    }

    assigned_ids: set[str] = set()

    for section in sections_sorted:
        section_id = section.get("id", "unknown")
        for item in items:
            item_id = item.get("id")
            if item_id in assigned_ids:
                continue
            if _section_matches(section, item):
                result[section_id].append(item)
                if item_id is not None:
                    assigned_ids.add(item_id)

    total_assigned = sum(len(v) for v in result.values())
    logger.info(
        "Categorized %d / %d items across %d sections",
        total_assigned,
        len(items),
        len(sections_sorted),
    )
    return result
