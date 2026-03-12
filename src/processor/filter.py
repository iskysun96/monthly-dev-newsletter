"""Filter aggregated items to remove noise before categorization."""

from __future__ import annotations

import logging
import re
from typing import Any

from src.utils.config_loader import load_newsletter_config

logger = logging.getLogger(__name__)


class _TitlePattern:
    """A compiled title-exclusion pattern with optional repo exceptions."""

    __slots__ = ("regex", "except_repos")

    def __init__(self, regex: re.Pattern[str], except_repos: list[str] | None = None):
        self.regex = regex
        self.except_repos = except_repos or []


def _compile_patterns(raw_patterns: list) -> list[re.Pattern[str]]:
    """Compile a list of regex strings, skipping any that are invalid."""
    compiled = []
    for pat in raw_patterns:
        try:
            compiled.append(re.compile(pat))
        except re.error as exc:
            logger.warning("Skipping invalid regex %r: %s", pat, exc)
    return compiled


def _compile_title_patterns(raw_patterns: list) -> list[_TitlePattern]:
    """Compile title-exclusion patterns.

    Each entry can be either a plain regex string or a dict with keys
    ``pattern`` and optionally ``except_repos`` (list of repo names
    to exempt from this filter).
    """
    compiled: list[_TitlePattern] = []
    for entry in raw_patterns:
        if isinstance(entry, dict):
            pat_str = entry.get("pattern", "")
            except_repos = entry.get("except_repos", [])
        else:
            pat_str = str(entry)
            except_repos = []
        try:
            compiled.append(_TitlePattern(re.compile(pat_str), except_repos))
        except re.error as exc:
            logger.warning("Skipping invalid regex %r: %s", pat_str, exc)
    return compiled


def _matches_any(value: str, patterns: list[re.Pattern[str]]) -> bool:
    """Return whether *value* matches any of the compiled *patterns*."""
    return any(p.search(value) for p in patterns)


def _title_matches_any(
    title: str, patterns: list[_TitlePattern], repo: str
) -> bool:
    """Return whether *title* matches any pattern, respecting repo exceptions."""
    for tp in patterns:
        if tp.regex.search(title):
            if repo and repo in tp.except_repos:
                continue
            return True
    return False


def filter_items(
    items: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return a new list with noisy items removed.

    Parameters
    ----------
    items:
        Aggregated items (not mutated).
    config:
        A newsletter config dict.  If *None*, the config is loaded
        automatically.

    Returns
    -------
    list[dict]
        Items that passed all filter checks.
    """
    if config is None:
        config = load_newsletter_config()

    filtering = config.get("filtering", {})
    if not filtering:
        return list(items)

    title_patterns = _compile_title_patterns(filtering.get("exclude_title_patterns", []))
    label_patterns = _compile_patterns(filtering.get("exclude_label_patterns", []))
    exclude_prerelease = filtering.get("exclude_prerelease", False)

    kept: list[dict[str, Any]] = []
    filtered_count = 0

    for item in items:
        title = item.get("title", "")
        labels = item.get("labels", [])
        prerelease = item.get("prerelease", False)
        repo = item.get("repo", "")

        # Check title exclusion
        if title_patterns and _title_matches_any(title, title_patterns, repo):
            logger.debug("Filtered (title): %s", title)
            filtered_count += 1
            continue

        # Check label exclusion
        if label_patterns and isinstance(labels, list):
            if any(_matches_any(label, label_patterns) for label in labels):
                logger.debug("Filtered (label): %s", title)
                filtered_count += 1
                continue

        # Check prerelease exclusion
        if exclude_prerelease and prerelease:
            logger.debug("Filtered (prerelease): %s", title)
            filtered_count += 1
            continue

        kept.append(item)

    logger.info(
        "Filtering: kept %d items, removed %d", len(kept), filtered_count
    )
    return kept
