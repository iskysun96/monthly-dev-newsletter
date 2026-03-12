"""GitHub API client factory with rate-limit awareness."""

from __future__ import annotations

import os
import logging
import time

from github import Github, RateLimitExceededException

logger = logging.getLogger(__name__)


def create_github_client() -> Github:
    """Create a PyGithub client using GH_SCRAPE_TOKEN from env."""
    token = os.environ.get("GH_SCRAPE_TOKEN", "")
    if not token:
        raise RuntimeError("GH_SCRAPE_TOKEN environment variable is not set")
    return Github(token, per_page=100)


def wait_for_rate_limit(client: Github) -> None:
    """Sleep until rate limit resets if remaining calls are low."""
    rate = client.get_rate_limit().rate
    if rate.remaining < 50:
        reset_at = rate.reset.timestamp()
        wait_seconds = max(reset_at - time.time(), 0) + 5
        logger.warning(
            "Rate limit low (%d remaining). Sleeping %.0fs until reset.",
            rate.remaining,
            wait_seconds,
        )
        time.sleep(wait_seconds)
