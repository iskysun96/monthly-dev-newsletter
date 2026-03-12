"""Tests for the aggregator module — merging weekly JSON files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.processor.aggregator import aggregate_month, load_weekly_file, _parse_item_date
from datetime import date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_weekly_file(
    directory: Path, filename: str, items: list[dict[str, Any]]
) -> Path:
    """Write a weekly JSON file in the expected format."""
    path = directory / filename
    path.write_text(json.dumps({"items": items}))
    return path


# ---------------------------------------------------------------------------
# load_weekly_file
# ---------------------------------------------------------------------------


class TestLoadWeeklyFile:
    def test_loads_valid_file(self, tmp_path):
        items = [{"id": "a", "title": "Item A"}]
        path = _write_weekly_file(tmp_path, "2026-W07-github-repos.json", items)

        loaded = load_weekly_file(path)
        assert loaded == items

    def test_missing_file_returns_empty(self, tmp_path):
        result = load_weekly_file(tmp_path / "nonexistent.json")
        assert result == []

    def test_malformed_json_returns_empty(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid json")
        result = load_weekly_file(path)
        assert result == []

    def test_items_not_a_list_returns_empty(self, tmp_path):
        path = tmp_path / "weird.json"
        path.write_text(json.dumps({"items": "not-a-list"}))
        result = load_weekly_file(path)
        assert result == []

    def test_missing_items_key_returns_empty(self, tmp_path):
        path = tmp_path / "no-items.json"
        path.write_text(json.dumps({"data": [1, 2, 3]}))
        result = load_weekly_file(path)
        assert result == []


# ---------------------------------------------------------------------------
# _parse_item_date
# ---------------------------------------------------------------------------


class TestParseItemDate:
    def test_iso_string(self):
        assert _parse_item_date({"date": "2026-02-15"}) == date(2026, 2, 15)

    def test_date_object(self):
        d = date(2026, 3, 1)
        assert _parse_item_date({"date": d}) == d

    def test_missing_date(self):
        assert _parse_item_date({}) is None

    def test_invalid_date_string(self):
        assert _parse_item_date({"date": "not-a-date"}) is None

    def test_iso_datetime_string_truncated(self):
        """A full ISO datetime is truncated to the first 10 chars (date part)."""
        assert _parse_item_date({"date": "2026-02-15T12:30:00Z"}) == date(2026, 2, 15)


# ---------------------------------------------------------------------------
# aggregate_month
# ---------------------------------------------------------------------------


class TestAggregateMonth:
    """Test the core aggregation logic using temporary fixture files."""

    @patch("src.processor.aggregator.iso_weeks_in_month")
    @patch("src.processor.aggregator.month_date_range")
    def test_merges_files_correctly(
        self, mock_date_range, mock_weeks, tmp_path
    ):
        """Items from multiple weekly files for the same month are merged."""
        mock_weeks.return_value = ["2026-W06", "2026-W07"]
        mock_date_range.return_value = (date(2026, 2, 1), date(2026, 2, 28))

        _write_weekly_file(tmp_path, "2026-W06-github-repos.json", [
            {"id": "r1", "date": "2026-02-05", "title": "Release 1"},
        ])
        _write_weekly_file(tmp_path, "2026-W07-github-repos.json", [
            {"id": "r2", "date": "2026-02-12", "title": "Release 2"},
        ])

        result = aggregate_month(2026, 2, data_dir=tmp_path)

        assert len(result) == 2
        ids = {item["id"] for item in result}
        assert ids == {"r1", "r2"}

    @patch("src.processor.aggregator.iso_weeks_in_month")
    @patch("src.processor.aggregator.month_date_range")
    def test_deduplication_by_id(
        self, mock_date_range, mock_weeks, tmp_path
    ):
        """Items with the same id appearing in multiple files are deduplicated."""
        mock_weeks.return_value = ["2026-W07"]
        mock_date_range.return_value = (date(2026, 2, 1), date(2026, 2, 28))

        _write_weekly_file(tmp_path, "2026-W07-github-repos.json", [
            {"id": "dup1", "date": "2026-02-10", "title": "Same Item"},
        ])
        _write_weekly_file(tmp_path, "2026-W07-web-content.json", [
            {"id": "dup1", "date": "2026-02-10", "title": "Same Item (duplicate)"},
        ])

        result = aggregate_month(2026, 2, data_dir=tmp_path)

        assert len(result) == 1
        assert result[0]["id"] == "dup1"

    @patch("src.processor.aggregator.iso_weeks_in_month")
    @patch("src.processor.aggregator.month_date_range")
    def test_date_filtering_excludes_out_of_month(
        self, mock_date_range, mock_weeks, tmp_path
    ):
        """Items with dates outside the target month are excluded."""
        mock_weeks.return_value = ["2026-W07"]
        mock_date_range.return_value = (date(2026, 2, 1), date(2026, 2, 28))

        _write_weekly_file(tmp_path, "2026-W07-github-repos.json", [
            {"id": "in_range", "date": "2026-02-15", "title": "In February"},
            {"id": "before_range", "date": "2026-01-31", "title": "In January"},
            {"id": "after_range", "date": "2026-03-01", "title": "In March"},
        ])

        result = aggregate_month(2026, 2, data_dir=tmp_path)

        assert len(result) == 1
        assert result[0]["id"] == "in_range"

    @patch("src.processor.aggregator.iso_weeks_in_month")
    @patch("src.processor.aggregator.month_date_range")
    def test_items_without_id_are_skipped(
        self, mock_date_range, mock_weeks, tmp_path
    ):
        """Items missing the 'id' field are silently skipped."""
        mock_weeks.return_value = ["2026-W07"]
        mock_date_range.return_value = (date(2026, 2, 1), date(2026, 2, 28))

        _write_weekly_file(tmp_path, "2026-W07-github-repos.json", [
            {"date": "2026-02-10", "title": "No ID"},
            {"id": "valid", "date": "2026-02-10", "title": "Has ID"},
        ])

        result = aggregate_month(2026, 2, data_dir=tmp_path)

        assert len(result) == 1
        assert result[0]["id"] == "valid"

    @patch("src.processor.aggregator.iso_weeks_in_month")
    @patch("src.processor.aggregator.month_date_range")
    def test_items_with_unparseable_date_are_skipped(
        self, mock_date_range, mock_weeks, tmp_path
    ):
        """Items whose date cannot be parsed are excluded."""
        mock_weeks.return_value = ["2026-W07"]
        mock_date_range.return_value = (date(2026, 2, 1), date(2026, 2, 28))

        _write_weekly_file(tmp_path, "2026-W07-github-repos.json", [
            {"id": "bad_date", "date": "not-a-date", "title": "Bad Date"},
            {"id": "good", "date": "2026-02-10", "title": "Good Date"},
        ])

        result = aggregate_month(2026, 2, data_dir=tmp_path)

        assert len(result) == 1
        assert result[0]["id"] == "good"

    @patch("src.processor.aggregator.iso_weeks_in_month")
    @patch("src.processor.aggregator.month_date_range")
    def test_missing_weekly_files_handled_gracefully(
        self, mock_date_range, mock_weeks, tmp_path
    ):
        """If no files exist for a week, aggregation still returns results
        from other weeks."""
        mock_weeks.return_value = ["2026-W06", "2026-W07", "2026-W08"]
        mock_date_range.return_value = (date(2026, 2, 1), date(2026, 2, 28))

        # Only W07 has files; W06 and W08 directories are empty
        _write_weekly_file(tmp_path, "2026-W07-github-repos.json", [
            {"id": "sole_item", "date": "2026-02-14", "title": "Only Item"},
        ])

        result = aggregate_month(2026, 2, data_dir=tmp_path)

        assert len(result) == 1
        assert result[0]["id"] == "sole_item"

    @patch("src.processor.aggregator.iso_weeks_in_month")
    @patch("src.processor.aggregator.month_date_range")
    def test_results_sorted_by_date_descending(
        self, mock_date_range, mock_weeks, tmp_path
    ):
        """Merged items are sorted by date descending, then by id descending."""
        mock_weeks.return_value = ["2026-W07"]
        mock_date_range.return_value = (date(2026, 2, 1), date(2026, 2, 28))

        _write_weekly_file(tmp_path, "2026-W07-github-repos.json", [
            {"id": "early", "date": "2026-02-05", "title": "Early"},
            {"id": "late", "date": "2026-02-25", "title": "Late"},
            {"id": "mid", "date": "2026-02-15", "title": "Mid"},
        ])

        result = aggregate_month(2026, 2, data_dir=tmp_path)

        dates = [item["date"] for item in result]
        assert dates == ["2026-02-25", "2026-02-15", "2026-02-05"]

    @patch("src.processor.aggregator.iso_weeks_in_month")
    @patch("src.processor.aggregator.month_date_range")
    def test_empty_data_dir_returns_empty(
        self, mock_date_range, mock_weeks, tmp_path
    ):
        """An empty data directory returns an empty list."""
        mock_weeks.return_value = ["2026-W07"]
        mock_date_range.return_value = (date(2026, 2, 1), date(2026, 2, 28))

        result = aggregate_month(2026, 2, data_dir=tmp_path)

        assert result == []
