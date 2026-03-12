"""Merge weekly JSON scrape files for a target month."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from src.utils.date_helpers import iso_weeks_in_month, month_date_range

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "weekly"


def load_weekly_file(path: Path) -> list[dict[str, Any]]:
    """Load items from a single weekly JSON file.

    Each file is expected to contain a JSON object with an ``items`` list.
    Returns an empty list if the file is missing, unreadable, or malformed.
    """
    try:
        with open(path) as f:
            data = json.load(f)
        items = data.get("items", [])
        if not isinstance(items, list):
            logger.warning("'items' in %s is not a list; skipping", path)
            return []
        return items
    except FileNotFoundError:
        logger.debug("Weekly file not found: %s", path)
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return []


def _parse_item_date(item: dict[str, Any]) -> date | None:
    """Parse the ``date`` field of an item into a :class:`datetime.date`.

    Accepts ``YYYY-MM-DD`` strings and returns *None* for missing or
    unparseable values.
    """
    raw = item.get("date")
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw)[:10])
    except (ValueError, TypeError):
        logger.debug("Unparseable date '%s' in item %s", raw, item.get("id"))
        return None


def aggregate_month(
    year: int,
    month: int,
    *,
    data_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Merge all weekly scrape files that overlap with *year*/*month*.

    Parameters
    ----------
    year:
        Calendar year (e.g. 2026).
    month:
        Calendar month (1--12).
    data_dir:
        Override the default ``data/weekly/`` directory (useful for testing).

    Returns
    -------
    list[dict]
        Deduplicated items whose ``date`` falls within the target month,
        sorted by date descending.
    """
    weekly_dir = data_dir if data_dir is not None else DATA_DIR
    weeks = iso_weeks_in_month(year, month)
    first_day, last_day = month_date_range(year, month)

    logger.info(
        "Aggregating month %04d-%02d (weeks %s)", year, month, ", ".join(weeks)
    )

    # Collect all matching weekly files via glob for each week.
    seen_ids: set[str] = set()
    merged: list[dict[str, Any]] = []

    for week in weeks:
        pattern = f"{week}-*.json"
        matched_files = sorted(weekly_dir.glob(pattern))
        if not matched_files:
            logger.debug("No files matched pattern %s", pattern)
        for path in matched_files:
            items = load_weekly_file(path)
            for item in items:
                item_id = item.get("id")
                if item_id is None:
                    logger.debug("Skipping item without id in %s", path)
                    continue
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                item_date = _parse_item_date(item)
                if item_date is None:
                    logger.debug(
                        "Skipping item %s with unparseable date", item_id
                    )
                    continue
                if first_day <= item_date <= last_day:
                    merged.append(item)

    # Sort by date descending; break ties by id for determinism.
    merged.sort(key=lambda it: (it.get("date", ""), it.get("id", "")), reverse=True)

    logger.info(
        "Aggregated %d unique items for %04d-%02d", len(merged), year, month
    )
    return merged
