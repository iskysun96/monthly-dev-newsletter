"""Tests for CHANGELOG.md scraping and minor PR tagging."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.scrapers.github_repos import GitHubReposScraper


class TestParseChangelogSections:
    """Test the static _parse_changelog_sections method."""

    def test_standard_keep_a_changelog_format(self):
        text = """\
# Changelog

## [1.2.3] - 2026-02-15

### Added
- New feature A
- New feature B

## [1.1.0] - 2026-01-10

### Fixed
- Bug fix X
"""
        sections = GitHubReposScraper._parse_changelog_sections(text)
        assert len(sections) == 2
        assert sections[0]["version"] == "1.2.3"
        assert sections[0]["date"] == date(2026, 2, 15)
        assert "New feature A" in sections[0]["body"]
        assert sections[1]["version"] == "1.1.0"
        assert sections[1]["date"] == date(2026, 1, 10)

    def test_v_prefix_format(self):
        text = """\
## v2.0.0 - 2026-03-01

Big changes here.

## v1.9.0 - 2026-02-01

Minor changes.
"""
        sections = GitHubReposScraper._parse_changelog_sections(text)
        assert len(sections) == 2
        assert sections[0]["version"] == "2.0.0"
        assert sections[0]["date"] == date(2026, 3, 1)

    def test_no_date_in_heading(self):
        text = """\
## [3.0.0]

Content without date.
"""
        sections = GitHubReposScraper._parse_changelog_sections(text)
        assert len(sections) == 1
        assert sections[0]["version"] == "3.0.0"
        assert sections[0]["date"] is None

    def test_empty_content(self):
        sections = GitHubReposScraper._parse_changelog_sections("")
        assert sections == []

    def test_no_version_headings(self):
        text = "# Changelog\n\nJust some text without version headings.\n"
        sections = GitHubReposScraper._parse_changelog_sections(text)
        assert sections == []

    def test_em_dash_separator(self):
        text = "## [1.0.0] — 2026-02-20\n\nContent.\n"
        sections = GitHubReposScraper._parse_changelog_sections(text)
        assert len(sections) == 1
        assert sections[0]["date"] == date(2026, 2, 20)

    def test_en_dash_separator(self):
        text = "## [1.0.0] \u2013 2026-02-20\n\nContent.\n"
        sections = GitHubReposScraper._parse_changelog_sections(text)
        assert len(sections) == 1
        assert sections[0]["date"] == date(2026, 2, 20)


class TestScrapeChangelog:
    """Test the _scrape_changelog method with mocked GitHub API."""

    @patch("src.scrapers.github_repos.load_repos_config")
    @patch("src.scrapers.github_repos.wait_for_rate_limit")
    def test_scrape_changelog_within_range(self, mock_wait, mock_config):
        mock_config.return_value = {
            "repos": [
                {
                    "owner": "aptos-labs",
                    "name": "aptos-ts-sdk",
                    "track": ["changelog"],
                }
            ]
        }

        changelog_content = """\
# Changelog

## [2.1.0] - 2026-02-15

### Added
- New transaction builder

## [2.0.0] - 2026-01-10

### Breaking
- Removed deprecated API
""".encode("utf-8")

        mock_contents = MagicMock()
        mock_contents.decoded_content = changelog_content

        mock_repo = MagicMock()
        mock_repo.full_name = "aptos-labs/aptos-ts-sdk"
        mock_repo.name = "aptos-ts-sdk"
        mock_repo.default_branch = "main"
        mock_repo.get_contents.return_value = mock_contents

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo

        scraper = GitHubReposScraper(client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        assert len(items) == 1
        assert items[0]["source_type"] == "changelog_entry"
        assert items[0]["title"] == "aptos-ts-sdk 2.1.0"
        assert "New transaction builder" in items[0]["body_full"]
        assert items[0]["version"] == "2.1.0"

    @patch("src.scrapers.github_repos.load_repos_config")
    @patch("src.scrapers.github_repos.wait_for_rate_limit")
    def test_scrape_changelog_no_file(self, mock_wait, mock_config):
        """Repos without CHANGELOG.md are skipped gracefully."""
        from github import GithubException

        mock_config.return_value = {
            "repos": [
                {
                    "owner": "aptos-labs",
                    "name": "aptos-core",
                    "track": ["changelog"],
                }
            ]
        }

        mock_repo = MagicMock()
        mock_repo.full_name = "aptos-labs/aptos-core"
        mock_repo.name = "aptos-core"
        mock_repo.get_contents.side_effect = GithubException(
            404, {"message": "Not Found"}, {}
        )

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo

        scraper = GitHubReposScraper(client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        assert items == []

    @patch("src.scrapers.github_repos.load_repos_config")
    @patch("src.scrapers.github_repos.wait_for_rate_limit")
    def test_scrape_changelog_entries_without_dates_skipped(
        self, mock_wait, mock_config
    ):
        """Changelog entries without parseable dates are skipped."""
        mock_config.return_value = {
            "repos": [
                {
                    "owner": "aptos-labs",
                    "name": "aptos-ts-sdk",
                    "track": ["changelog"],
                }
            ]
        }

        changelog_content = """\
# Changelog

## [Unreleased]

### Added
- Work in progress

## [2.1.0]

### Added
- New API (no date in heading)
""".encode("utf-8")

        mock_contents = MagicMock()
        mock_contents.decoded_content = changelog_content

        mock_repo = MagicMock()
        mock_repo.full_name = "aptos-labs/aptos-ts-sdk"
        mock_repo.name = "aptos-ts-sdk"
        mock_repo.default_branch = "main"
        mock_repo.get_contents.return_value = mock_contents

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo

        scraper = GitHubReposScraper(client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        # Both entries have no date, so both are skipped
        assert items == []


class TestBodyFullOnReleases:
    """Verify that releases now include body_full."""

    @patch("src.scrapers.github_repos.load_repos_config")
    @patch("src.scrapers.github_repos.wait_for_rate_limit")
    def test_release_has_body_full(self, mock_wait, mock_config):
        mock_config.return_value = {
            "repos": [
                {
                    "owner": "aptos-labs",
                    "name": "aptos-core",
                    "track": ["releases"],
                }
            ]
        }

        long_body = "A" * 5000
        mock_release = MagicMock()
        mock_release.published_at = datetime(2026, 2, 15, 12, 0, tzinfo=timezone.utc)
        mock_release.tag_name = "v1.0.0"
        mock_release.body = long_body
        mock_release.html_url = "https://example.com"
        mock_release.prerelease = False

        mock_repo = MagicMock()
        mock_repo.full_name = "aptos-labs/aptos-core"
        mock_repo.name = "aptos-core"
        mock_repo.get_releases.return_value = [mock_release]

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo

        scraper = GitHubReposScraper(client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        assert len(items) == 1
        # body is truncated to 2000
        assert len(items[0]["body"]) == 2000
        # body_full has the full content
        assert len(items[0]["body_full"]) == 5000


class TestMinorPRTagging:
    """Verify that PRs below min_files are tagged as minor."""

    @patch("src.scrapers.github_repos.load_repos_config")
    @patch("src.scrapers.github_repos.wait_for_rate_limit")
    def test_pr_above_min_files_not_minor(self, mock_wait, mock_config):
        mock_config.return_value = {
            "repos": [
                {
                    "owner": "aptos-labs",
                    "name": "aptos-core",
                    "track": ["prs"],
                    "pr_min_files": 5,
                }
            ]
        }

        mock_pr = MagicMock()
        mock_pr.updated_at = datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc)
        mock_pr.merged = True
        mock_pr.merged_at = datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc)
        mock_pr.number = 42
        mock_pr.title = "Big PR"
        mock_pr.body = "Description"
        mock_pr.html_url = "https://example.com/pull/42"
        mock_pr.labels = []
        mock_pr.changed_files = 10
        mock_pr.additions = 100
        mock_pr.deletions = 50

        mock_repo = MagicMock()
        mock_repo.full_name = "aptos-labs/aptos-core"
        mock_repo.get_pulls.return_value = [mock_pr]

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo

        scraper = GitHubReposScraper(client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        assert len(items) == 1
        assert items[0]["minor"] is False

    @patch("src.scrapers.github_repos.load_repos_config")
    @patch("src.scrapers.github_repos.wait_for_rate_limit")
    def test_pr_with_no_min_files_not_minor(self, mock_wait, mock_config):
        mock_config.return_value = {
            "repos": [
                {
                    "owner": "aptos-labs",
                    "name": "aptos-ts-sdk",
                    "track": ["prs"],
                    "pr_min_files": 0,
                }
            ]
        }

        mock_pr = MagicMock()
        mock_pr.updated_at = datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc)
        mock_pr.merged = True
        mock_pr.merged_at = datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc)
        mock_pr.number = 1
        mock_pr.title = "Tiny fix"
        mock_pr.body = "One line change"
        mock_pr.html_url = "https://example.com/pull/1"
        mock_pr.labels = []
        mock_pr.changed_files = 1
        mock_pr.additions = 1
        mock_pr.deletions = 0

        mock_repo = MagicMock()
        mock_repo.full_name = "aptos-labs/aptos-ts-sdk"
        mock_repo.get_pulls.return_value = [mock_pr]

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo

        scraper = GitHubReposScraper(client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        assert len(items) == 1
        # min_files=0 means no minimum, so not minor
        assert items[0]["minor"] is False


class TestMinorPRFilter:
    """Verify that the filter excludes minor PRs."""

    def test_minor_prs_filtered_out(self):
        from src.processor.filter import filter_items

        items = [
            {"id": "1", "title": "Small fix", "minor": True},
            {"id": "2", "title": "feat: big feature", "minor": False},
            {"id": "3", "title": "Another big one"},
        ]
        config = {"filtering": {}}
        result = filter_items(items, config=config)

        # Only minor=True items should be excluded
        assert len(result) == 2
        assert result[0]["id"] == "2"
        assert result[1]["id"] == "3"
