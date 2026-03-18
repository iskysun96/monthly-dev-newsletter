#!/usr/bin/env python3
"""One-command newsletter generation.

Scrapes all weeks for a target month, then generates the newsletter.

Usage:
    # Generate for the previous month (default)
    python scripts/generate_newsletter.py

    # Generate for a specific month
    python scripts/generate_newsletter.py 2026-02

    # Scrape only (skip newsletter generation)
    python scripts/generate_newsletter.py 2026-02 --scrape-only

    # Generate only (skip scraping, use existing weekly data)
    python scripts/generate_newsletter.py 2026-02 --generate-only

    # Dry run (scrape + categorize, but skip Claude summarization and rendering)
    python scripts/generate_newsletter.py 2026-02 --dry-run

    # Skip Claude summarization (render with raw bullet lists)
    python scripts/generate_newsletter.py 2026-02 --skip-summarize
"""

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from src.scrapers.github_repos import GitHubReposScraper
from src.scrapers.github_aips import GitHubAIPsScraper
from src.scrapers.web_content import WebContentScraper
from src.scrapers.youtube import YouTubeScraper
from src.scrapers.governance import GovernanceScraper
from src.utils.date_helpers import (
    iso_week_date_range,
    iso_weeks_in_month,
    parse_month_string,
    previous_month,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data" / "weekly"

SCRAPER_CLASSES = [
    GitHubReposScraper,
    GitHubAIPsScraper,
    WebContentScraper,
    YouTubeScraper,
    GovernanceScraper,
]


def save_results(iso_week: str, scraper_name: str, items: list) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{iso_week}-{scraper_name}.json"
    path = DATA_DIR / filename
    with open(path, "w") as f:
        json.dump({"week": iso_week, "scraper": scraper_name, "items": items}, f, indent=2)
    logger.info("Saved %d items to %s", len(items), path)
    return path


def scrape_month(year: int, month: int) -> int:
    """Run all scrapers for every ISO week overlapping the target month."""
    weeks = iso_weeks_in_month(year, month)
    logger.info("Scraping %d weeks for %d-%02d: %s", len(weeks), year, month, ", ".join(weeks))

    total = 0
    for week in weeks:
        # Skip weeks that already have data
        existing = list(DATA_DIR.glob(f"{week}-*.json"))
        if existing:
            logger.info("Week %s already scraped (%d files), skipping", week, len(existing))
            total += sum(
                len(json.loads(f.read_text()).get("items", []))
                for f in existing
            )
            continue

        since, until = iso_week_date_range(week)
        logger.info("Scraping week %s (%s to %s)", week, since, until)

        for scraper_cls in SCRAPER_CLASSES:
            try:
                scraper = scraper_cls()
                items = scraper.scrape(since, until)
                save_results(week, scraper.name, items)
                total += len(items)
            except Exception:
                logger.exception("Scraper %s failed for %s", scraper_cls.__name__, week)

    return total


def generate(year: int, month: int, dry_run: bool = False, skip_summarize: bool = False) -> None:
    """Run the monthly newsletter generation pipeline."""
    import os
    os.environ["MONTH_OVERRIDE"] = f"{year}-{month:02d}"
    if dry_run:
        os.environ["DRY_RUN"] = "true"
    if skip_summarize:
        os.environ["SKIP_SUMMARIZE"] = "true"

    # Import and run the existing generation script
    from scripts.run_monthly_generate import main as generate_main
    generate_main()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Aptos developer newsletter (scrape + generate in one step)"
    )
    parser.add_argument(
        "month",
        nargs="?",
        help="Target month as YYYY-MM (default: previous month)",
    )
    parser.add_argument(
        "--scrape-only",
        action="store_true",
        help="Only scrape weekly data, skip newsletter generation",
    )
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Only generate newsletter from existing weekly data",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and categorize, but skip Claude summarization and rendering",
    )
    parser.add_argument(
        "--skip-summarize",
        action="store_true",
        help="Generate newsletter with raw bullet lists instead of Claude summaries",
    )
    parser.add_argument(
        "--force-scrape",
        action="store_true",
        help="Re-scrape weeks even if data already exists",
    )
    args = parser.parse_args()

    if args.month:
        year, month = parse_month_string(args.month)
    else:
        year, month = previous_month()

    month_year = f"{year}-{month:02d}"

    if args.force_scrape:
        # Remove existing weekly data for this month's weeks
        weeks = iso_weeks_in_month(year, month)
        for week in weeks:
            for f in DATA_DIR.glob(f"{week}-*.json"):
                f.unlink()
                logger.info("Removed %s", f)

    if not args.generate_only:
        logger.info("=== Scraping weekly data for %s ===", month_year)
        total = scrape_month(year, month)
        logger.info("Scraping complete: %d total items", total)

    if not args.scrape_only:
        logger.info("=== Generating newsletter for %s ===", month_year)
        generate(year, month, dry_run=args.dry_run, skip_summarize=args.skip_summarize)


if __name__ == "__main__":
    main()
