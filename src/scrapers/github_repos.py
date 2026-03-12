"""Scraper for GitHub repos: releases, merged PRs, and notable commits."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Any

from github import Github
from github.Repository import Repository

from src.scrapers.base import BaseScraper
from src.utils.config_loader import load_repos_config
from src.utils.github_client import create_github_client, wait_for_rate_limit

logger = logging.getLogger(__name__)


class GitHubReposScraper(BaseScraper):
    name = "github-repos"

    def __init__(self, client: Github | None = None):
        self.client = client or create_github_client()
        self.config = load_repos_config()

    def scrape(self, since: date, until: date) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        since_dt = datetime.combine(since, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )
        until_dt = datetime.combine(until, datetime.max.time()).replace(
            tzinfo=timezone.utc
        )

        for repo_cfg in self.config["repos"]:
            full_name = f"{repo_cfg['owner']}/{repo_cfg['name']}"
            logger.info("Scraping %s", full_name)
            wait_for_rate_limit(self.client)

            try:
                repo = self.client.get_repo(full_name)
            except Exception:
                logger.exception("Failed to access repo %s", full_name)
                continue

            track = repo_cfg.get("track", [])

            if "releases" in track:
                items.extend(self._scrape_releases(repo, since_dt, until_dt))

            if "prs" in track:
                pr_min_files = repo_cfg.get("pr_min_files", 0)
                items.extend(
                    self._scrape_prs(repo, since_dt, until_dt, pr_min_files)
                )

            if "commits" in track:
                prefixes = repo_cfg.get("commit_prefixes", [])
                items.extend(
                    self._scrape_commits(repo, since_dt, until_dt, prefixes)
                )

        return items

    def _scrape_releases(
        self, repo: Repository, since: datetime, until: datetime
    ) -> list[dict[str, Any]]:
        items = []
        for release in repo.get_releases():
            published = release.published_at
            if published is None:
                continue
            if published < since:
                break
            if published > until:
                continue
            items.append(
                {
                    "id": f"release:{repo.full_name}:{release.tag_name}",
                    "source_type": "release",
                    "title": f"{repo.name} {release.tag_name}",
                    "body": (release.body or "")[:2000],
                    "url": release.html_url,
                    "date": published.date().isoformat(),
                    "repo": repo.full_name,
                    "tag": release.tag_name,
                    "prerelease": release.prerelease,
                }
            )
        return items

    def _scrape_prs(
        self,
        repo: Repository,
        since: datetime,
        until: datetime,
        min_files: int,
    ) -> list[dict[str, Any]]:
        items = []
        prs = repo.get_pulls(state="closed", sort="updated", direction="desc")
        for pr in prs:
            if pr.updated_at < since:
                break
            if not pr.merged or pr.merged_at is None:
                continue
            if pr.merged_at < since or pr.merged_at > until:
                continue
            if min_files > 0 and pr.changed_files < min_files:
                continue
            labels = [l.name for l in pr.labels]
            items.append(
                {
                    "id": f"pr:{repo.full_name}:#{pr.number}",
                    "source_type": "pr",
                    "title": pr.title,
                    "body": (pr.body or "")[:2000],
                    "url": pr.html_url,
                    "date": pr.merged_at.date().isoformat(),
                    "repo": repo.full_name,
                    "number": pr.number,
                    "labels": labels,
                    "changed_files": pr.changed_files,
                    "additions": pr.additions,
                    "deletions": pr.deletions,
                }
            )
            wait_for_rate_limit(self.client)
        return items

    def _scrape_commits(
        self,
        repo: Repository,
        since: datetime,
        until: datetime,
        prefixes: list[str],
    ) -> list[dict[str, Any]]:
        items = []
        if not prefixes:
            return items
        pattern = "|".join(re.escape(p) for p in prefixes)
        regex = re.compile(f"^({pattern})", re.IGNORECASE)

        commits = repo.get_commits(since=since, until=until)
        for commit in commits:
            msg = commit.commit.message.split("\n")[0]
            if not regex.match(msg):
                continue
            commit_date = commit.commit.committer.date
            items.append(
                {
                    "id": f"commit:{repo.full_name}:{commit.sha[:12]}",
                    "source_type": "commit",
                    "title": msg,
                    "url": commit.html_url,
                    "date": commit_date.date().isoformat(),
                    "repo": repo.full_name,
                    "sha": commit.sha,
                }
            )
            wait_for_rate_limit(self.client)
        return items
