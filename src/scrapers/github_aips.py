"""Scraper for Aptos Improvement Proposals from aptos-foundation/AIPs."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from github import Github

from src.scrapers.base import BaseScraper
from src.utils.config_loader import load_sources_config
from src.utils.github_client import create_github_client, wait_for_rate_limit

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
STATE_FILE = DATA_DIR / "state.json"


def _load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_scrape": None, "etags": {}, "known_aips": {}}


def _save_state(state: dict[str, Any]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _parse_aip_frontmatter(content: str) -> dict[str, str]:
    """Extract YAML-like frontmatter from an AIP markdown file."""
    metadata: dict[str, str] = {}
    lines = content.split("\n")
    in_frontmatter = False
    for line in lines:
        stripped = line.strip()
        if stripped == "---":
            if in_frontmatter:
                break
            in_frontmatter = True
            continue
        if in_frontmatter and ":" in stripped:
            key, _, value = stripped.partition(":")
            metadata[key.strip().lower()] = value.strip().strip('"').strip("'")
    return metadata


class GitHubAIPsScraper(BaseScraper):
    name = "github-aips"

    def __init__(self, client: Github | None = None):
        self.client = client or create_github_client()
        self.config = load_sources_config()["aips"]

    def scrape(self, since: date, until: date) -> list[dict[str, Any]]:
        state = _load_state()
        known_aips = state.get("known_aips", {})

        full_name = f"{self.config['owner']}/{self.config['name']}"
        logger.info("Scraping AIPs from %s", full_name)
        wait_for_rate_limit(self.client)

        try:
            repo = self.client.get_repo(full_name)
        except Exception:
            logger.exception("Failed to access AIP repo %s", full_name)
            return []

        items: list[dict[str, Any]] = []
        aip_path = self.config.get("path", "aips")

        try:
            contents = repo.get_contents(aip_path, ref=self.config.get("branch", "main"))
        except Exception:
            logger.exception("Failed to list AIP directory")
            return []

        if not isinstance(contents, list):
            contents = [contents]

        for entry in contents:
            if not entry.name.lower().endswith(".md"):
                continue

            aip_match = re.search(r"aip-(\d+)", entry.name, re.IGNORECASE)
            if not aip_match:
                continue

            aip_number = aip_match.group(1)
            current_sha = entry.sha
            prev_sha = known_aips.get(aip_number)

            if prev_sha == current_sha:
                continue

            is_new = aip_number not in known_aips
            known_aips[aip_number] = current_sha

            try:
                file_content = entry.decoded_content.decode("utf-8")
            except Exception:
                logger.warning("Could not decode AIP-%s", aip_number)
                continue

            metadata = _parse_aip_frontmatter(file_content)
            title = metadata.get("title", f"AIP-{aip_number}")
            status = metadata.get("status", "Unknown")

            # Use last commit date for this file as the date
            commits = repo.get_commits(path=entry.path, sha=self.config.get("branch", "main"))
            try:
                last_commit = commits[0]
                item_date = last_commit.commit.committer.date.date()
            except Exception:
                item_date = date.today()

            if item_date < since or item_date > until:
                continue

            items.append(
                {
                    "id": f"aip:{aip_number}:{current_sha[:12]}",
                    "source_type": "aip",
                    "title": f"AIP-{aip_number}: {title}",
                    "url": f"https://github.com/{full_name}/blob/main/{entry.path}",
                    "date": item_date.isoformat(),
                    "repo": full_name,
                    "aip_number": int(aip_number),
                    "status": status,
                    "is_new": is_new,
                }
            )
            wait_for_rate_limit(self.client)

        state["known_aips"] = known_aips
        _save_state(state)

        return items
