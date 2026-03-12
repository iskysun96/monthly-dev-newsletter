#!/usr/bin/env python3
"""Monthly newsletter generation entry point.

Aggregates weekly scrape data, categorizes items, generates
Claude summaries, and renders Markdown + HTML output.
"""

import logging
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from src.processor.aggregator import aggregate_month
from src.processor.filter import filter_items
from src.processor.categorizer import categorize
from src.generator.summarizer import generate_all_summaries
from src.generator.renderer import render_markdown, render_html, save_output
from src.utils.date_helpers import parse_month_string, previous_month

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _print_dry_run(categorized: dict, month_year: str) -> None:
    """Print a console summary of categorized items for dry-run mode."""
    print(f"\n{'=' * 60}")
    print(f"DRY RUN — Newsletter for {month_year}")
    print(f"{'=' * 60}\n")

    total = 0
    for section_id, items in categorized.items():
        if not items:
            continue
        print(f"## {section_id} ({len(items)} items)")
        for item in items:
            source_type = item.get("source_type", "item")
            repo = item.get("repo", "")
            date = item.get("date", "")
            title = item.get("title", "")
            meta_parts = [source_type]
            if repo:
                meta_parts.append(repo)
            if date:
                meta_parts.append(date)
            print(f"  - {title}")
            print(f"    [{' | '.join(meta_parts)}]")
        print()
        total += len(items)

    print(f"{'=' * 60}")
    print(f"Total items: {total}")
    print(f"{'=' * 60}\n")


def main() -> None:
    month_override = os.environ.get("MONTH_OVERRIDE", "")
    if month_override:
        year, month = parse_month_string(month_override)
    else:
        year, month = previous_month()

    month_year = f"{year}-{month:02d}"
    logger.info("Generating newsletter for %s", month_year)

    dry_run = os.environ.get("DRY_RUN", "").lower() in ("true", "1", "yes")

    # Step 1: Aggregate weekly data
    items = aggregate_month(year, month)
    logger.info("Aggregated %d items for %s", len(items), month_year)

    if not items:
        logger.warning("No items found for %s. Exiting.", month_year)
        return

    # Step 2: Filter noise
    items = filter_items(items)
    logger.info("After filtering: %d items", len(items))

    if not items:
        logger.warning("All items filtered for %s. Exiting.", month_year)
        return

    # Step 3: Categorize into sections
    categorized = categorize(items)
    for section_id, section_items in categorized.items():
        logger.info("  %s: %d items", section_id, len(section_items))

    # Dry-run mode: print summary and exit
    if dry_run:
        _print_dry_run(categorized, month_year)
        return

    # Step 4: Generate summaries
    skip_summarize = os.environ.get("SKIP_SUMMARIZE", "").lower() in ("true", "1", "yes")
    summaries = generate_all_summaries(categorized, month_year, skip=skip_summarize)

    # Step 5: Render output
    markdown = render_markdown(summaries, categorized, month_year)
    html = render_html(summaries, categorized, month_year)

    # Step 6: Save
    md_path, html_path = save_output(month_year, markdown, html)
    logger.info("Newsletter generated successfully:")
    logger.info("  Markdown: %s", md_path)
    logger.info("  HTML:     %s", html_path)


if __name__ == "__main__":
    main()
