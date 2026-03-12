"""Abstract base class for all scrapers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any


class BaseScraper(ABC):
    """Base class that all scrapers must implement."""

    @abstractmethod
    def scrape(self, since: date, until: date) -> list[dict[str, Any]]:
        """Scrape items within the given date range.

        Returns a list of dicts, each with at minimum:
        - id: str — unique identifier
        - source_type: str — e.g. "release", "pr", "commit", "aip", "blog", "forum"
        - title: str
        - url: str
        - date: str — ISO 8601 date
        - repo: str — "owner/name" (for GitHub items) or source name
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Short name for this scraper, used in filenames."""
        ...
