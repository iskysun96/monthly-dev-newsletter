"""ISO week and month range utilities."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta


def current_iso_week() -> str:
    """Return current ISO week string like '2026-W11'."""
    today = date.today()
    return f"{today.isocalendar().year}-W{today.isocalendar().week:02d}"


def iso_week_date_range(iso_week: str) -> tuple[date, date]:
    """Return (monday, sunday) for a given ISO week string like '2026-W11'."""
    monday = datetime.strptime(f"{iso_week}-1", "%G-W%V-%u").date()
    sunday = monday + timedelta(days=6)
    return monday, sunday


def month_date_range(year: int, month: int) -> tuple[date, date]:
    """Return (first_day, last_day) for a given year and month."""
    first = date(year, month, 1)
    last = first + relativedelta(months=1) - timedelta(days=1)
    return first, last


def iso_weeks_in_month(year: int, month: int) -> list[str]:
    """Return all ISO week strings that overlap with the given month."""
    first, last = month_date_range(year, month)
    weeks = set()
    current = first
    while current <= last:
        cal = current.isocalendar()
        weeks.add(f"{cal.year}-W{cal.week:02d}")
        current += timedelta(days=1)
    return sorted(weeks)


def parse_month_string(month_str: str) -> tuple[int, int]:
    """Parse 'YYYY-MM' into (year, month)."""
    parts = month_str.split("-")
    return int(parts[0]), int(parts[1])


def previous_month() -> tuple[int, int]:
    """Return (year, month) for the previous month."""
    today = date.today()
    prev = today.replace(day=1) - timedelta(days=1)
    return prev.year, prev.month
