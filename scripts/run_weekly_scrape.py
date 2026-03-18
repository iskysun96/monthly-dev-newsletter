#!/usr/bin/env python3
"""Weekly scrape entry point.

Runs all scrapers for the current ISO week (or WEEK_OVERRIDE)
and saves results as JSON in data/weekly/.
"""

import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from src.scrapers.github_repos import GitHubReposScraper
from src.scrapers.github_aips import GitHubAIPsScraper
from src.scrapers.web_content import WebContentScraper
from src.scrapers.youtube import YouTubeScraper
from src.scrapers.governance import GovernanceScraper
from src.utils.date_helpers import current_iso_week, iso_week_date_range

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data" / "weekly"


def save_results(iso_week: str, scraper_name: str, items: list) -> Path:
    """Save scraper results to a JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{iso_week}-{scraper_name}.json"
    path = DATA_DIR / filename
    with open(path, "w") as f:
        json.dump({"week": iso_week, "scraper": scraper_name, "items": items}, f, indent=2)
    logger.info("Saved %d items to %s", len(items), path)
    return path


def main() -> None:
    iso_week = os.environ.get("WEEK_OVERRIDE") or current_iso_week()
    logger.info("Running weekly scrape for %s", iso_week)

    since, until = iso_week_date_range(iso_week)
    logger.info("Date range: %s to %s", since, until)

    scraper_classes = [
        GitHubReposScraper,
        GitHubAIPsScraper,
        WebContentScraper,
        YouTubeScraper,
        GovernanceScraper,
    ]

    total = 0
    for scraper_cls in scraper_classes:
        try:
            scraper = scraper_cls()
            logger.info("Running scraper: %s", scraper.name)
            items = scraper.scrape(since, until)
            save_results(iso_week, scraper.name, items)
            total += len(items)
        except Exception:
            logger.exception("Scraper %s failed", scraper_cls.__name__)

    logger.info("Weekly scrape complete. Total items: %d", total)


if __name__ == "__main__":
    main()
