"""Scraper for GitHub repos: releases, merged PRs, notable commits, and changelogs."""

from __future__ import annotations

import base64
import logging
import re
from datetime import date, datetime, timezone
from typing import Any

from github import Github, GithubException
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

            if "changelog" in track:
                items.extend(
                    self._scrape_changelog(repo, since_dt, until_dt)
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
                    "body_full": release.body or "",
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
            minor = min_files > 0 and pr.changed_files < min_files
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
                    "minor": minor,
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

    def _scrape_changelog(
        self,
        repo: Repository,
        since: datetime,
        until: datetime,
    ) -> list[dict[str, Any]]:
        """Scrape CHANGELOG.md for version entries within the date range."""
        items = []
        try:
            contents = repo.get_contents("CHANGELOG.md")
        except GithubException:
            logger.debug("No CHANGELOG.md in %s", repo.full_name)
            return items

        if isinstance(contents, list):
            return items

        text = contents.decoded_content.decode("utf-8", errors="replace")
        entries = self._parse_changelog_sections(text)

        since_date = since.date() if isinstance(since, datetime) else since
        until_date = until.date() if isinstance(until, datetime) else until

        for entry in entries:
            entry_date = entry.get("date")
            if entry_date is None:
                continue
            if entry_date < since_date or entry_date > until_date:
                continue
            items.append(
                {
                    "id": f"changelog:{repo.full_name}:{entry['version']}",
                    "source_type": "changelog_entry",
                    "title": f"{repo.name} {entry['version']}",
                    "body": entry["body"][:2000],
                    "body_full": entry["body"],
                    "url": f"https://github.com/{repo.full_name}/blob/{repo.default_branch}/CHANGELOG.md",
                    "date": entry_date.isoformat(),
                    "repo": repo.full_name,
                    "version": entry["version"],
                }
            )

        return items

    @staticmethod
    def _parse_changelog_sections(text: str) -> list[dict[str, Any]]:
        """Parse version sections from a CHANGELOG.md file.

        Recognises headings like ``## [1.2.3]``, ``## v1.2.3``,
        ``## [1.2.3] - 2026-03-01`` etc.
        """
        heading_re = re.compile(
            r"^##\s+\[?v?(\d+\.\d+[^\]\s]*)\]?"
            r"(?:\s*[-–—]\s*(\d{4}-\d{2}-\d{2}))?",
            re.MULTILINE,
        )
        sections: list[dict[str, Any]] = []
        matches = list(heading_re.finditer(text))

        for i, m in enumerate(matches):
            version = m.group(1).strip()
            date_str = m.group(2)
            entry_date = None
            if date_str:
                try:
                    entry_date = date.fromisoformat(date_str)
                except ValueError:
                    pass

            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()

            sections.append(
                {"version": version, "date": entry_date, "body": body}
            )

        return sections
