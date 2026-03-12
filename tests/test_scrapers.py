"""Tests for scraper base class and concrete scraper implementations."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.scrapers.base import BaseScraper
from src.scrapers.github_aips import _parse_aip_frontmatter


# ---------------------------------------------------------------------------
# BaseScraper abstract interface
# ---------------------------------------------------------------------------


class TestBaseScraper:
    """Verify the abstract base class contract."""

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseScraper()

    def test_concrete_subclass_requires_scrape_and_name(self):
        """A subclass must implement both `scrape` and `name`."""

        class IncompleteScraper(BaseScraper):
            name = "incomplete"

        with pytest.raises(TypeError):
            IncompleteScraper()

    def test_concrete_subclass_can_be_instantiated(self):
        class ValidScraper(BaseScraper):
            name = "valid"

            def scrape(self, since, until):
                return []

        scraper = ValidScraper()
        assert scraper.name == "valid"
        assert scraper.scrape(date(2026, 1, 1), date(2026, 1, 31)) == []


# ---------------------------------------------------------------------------
# GitHubReposScraper
# ---------------------------------------------------------------------------


class TestGitHubReposScraper:
    """Test GitHubReposScraper using mocked GitHub API objects."""

    @patch("src.scrapers.github_repos.load_repos_config")
    @patch("src.scrapers.github_repos.wait_for_rate_limit")
    def test_scrape_releases_constructs_items(
        self, mock_wait, mock_config
    ):
        """Releases within the date range are collected with correct fields."""
        mock_config.return_value = {
            "repos": [
                {
                    "owner": "aptos-labs",
                    "name": "aptos-core",
                    "track": ["releases"],
                }
            ]
        }

        mock_release = MagicMock()
        mock_release.published_at = datetime(2026, 2, 15, 12, 0, tzinfo=timezone.utc)
        mock_release.tag_name = "v1.2.3"
        mock_release.body = "Release notes here"
        mock_release.html_url = "https://github.com/aptos-labs/aptos-core/releases/tag/v1.2.3"
        mock_release.prerelease = False

        mock_repo = MagicMock()
        mock_repo.full_name = "aptos-labs/aptos-core"
        mock_repo.name = "aptos-core"
        mock_repo.get_releases.return_value = [mock_release]

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo

        from src.scrapers.github_repos import GitHubReposScraper

        scraper = GitHubReposScraper(client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        assert len(items) == 1
        item = items[0]
        assert item["id"] == "release:aptos-labs/aptos-core:v1.2.3"
        assert item["source_type"] == "release"
        assert item["title"] == "aptos-core v1.2.3"
        assert item["url"] == mock_release.html_url
        assert item["date"] == "2026-02-15"
        assert item["repo"] == "aptos-labs/aptos-core"
        assert item["tag"] == "v1.2.3"
        assert item["prerelease"] is False

    @patch("src.scrapers.github_repos.load_repos_config")
    @patch("src.scrapers.github_repos.wait_for_rate_limit")
    def test_scrape_releases_skips_outside_range(
        self, mock_wait, mock_config
    ):
        """Releases outside the date range are excluded."""
        mock_config.return_value = {
            "repos": [
                {
                    "owner": "aptos-labs",
                    "name": "aptos-core",
                    "track": ["releases"],
                }
            ]
        }

        # Release after the range
        future_release = MagicMock()
        future_release.published_at = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        future_release.tag_name = "v2.0.0"

        # Release before the range (triggers the break)
        old_release = MagicMock()
        old_release.published_at = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        old_release.tag_name = "v0.9.0"

        mock_repo = MagicMock()
        mock_repo.full_name = "aptos-labs/aptos-core"
        mock_repo.name = "aptos-core"
        mock_repo.get_releases.return_value = [future_release, old_release]

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo

        from src.scrapers.github_repos import GitHubReposScraper

        scraper = GitHubReposScraper(client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        assert len(items) == 0

    @patch("src.scrapers.github_repos.load_repos_config")
    @patch("src.scrapers.github_repos.wait_for_rate_limit")
    def test_scrape_prs_constructs_items(
        self, mock_wait, mock_config
    ):
        """Merged PRs within the date range are collected with correct fields."""
        mock_config.return_value = {
            "repos": [
                {
                    "owner": "aptos-labs",
                    "name": "aptos-core",
                    "track": ["prs"],
                    "pr_min_files": 0,
                }
            ]
        }

        mock_label = MagicMock()
        mock_label.name = "consensus"

        mock_pr = MagicMock()
        mock_pr.updated_at = datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc)
        mock_pr.merged = True
        mock_pr.merged_at = datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc)
        mock_pr.number = 42
        mock_pr.title = "Improve consensus throughput"
        mock_pr.body = "Detailed description"
        mock_pr.html_url = "https://github.com/aptos-labs/aptos-core/pull/42"
        mock_pr.labels = [mock_label]
        mock_pr.changed_files = 5
        mock_pr.additions = 100
        mock_pr.deletions = 20

        mock_repo = MagicMock()
        mock_repo.full_name = "aptos-labs/aptos-core"
        mock_repo.get_pulls.return_value = [mock_pr]

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo

        from src.scrapers.github_repos import GitHubReposScraper

        scraper = GitHubReposScraper(client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        assert len(items) == 1
        item = items[0]
        assert item["id"] == "pr:aptos-labs/aptos-core:#42"
        assert item["source_type"] == "pr"
        assert item["title"] == "Improve consensus throughput"
        assert item["labels"] == ["consensus"]
        assert item["changed_files"] == 5

    @patch("src.scrapers.github_repos.load_repos_config")
    @patch("src.scrapers.github_repos.wait_for_rate_limit")
    def test_scrape_prs_filters_by_min_files(
        self, mock_wait, mock_config
    ):
        """PRs with fewer changed files than pr_min_files are excluded."""
        mock_config.return_value = {
            "repos": [
                {
                    "owner": "aptos-labs",
                    "name": "aptos-core",
                    "track": ["prs"],
                    "pr_min_files": 10,
                }
            ]
        }

        mock_pr = MagicMock()
        mock_pr.updated_at = datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc)
        mock_pr.merged = True
        mock_pr.merged_at = datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc)
        mock_pr.number = 99
        mock_pr.changed_files = 3  # Below threshold of 10

        mock_repo = MagicMock()
        mock_repo.full_name = "aptos-labs/aptos-core"
        mock_repo.get_pulls.return_value = [mock_pr]

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo

        from src.scrapers.github_repos import GitHubReposScraper

        scraper = GitHubReposScraper(client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        assert len(items) == 0

    @patch("src.scrapers.github_repos.load_repos_config")
    @patch("src.scrapers.github_repos.wait_for_rate_limit")
    def test_scrape_commits_matches_prefixes(
        self, mock_wait, mock_config
    ):
        """Commits matching configured prefixes are collected."""
        mock_config.return_value = {
            "repos": [
                {
                    "owner": "aptos-labs",
                    "name": "aptos-core",
                    "track": ["commits"],
                    "commit_prefixes": ["feat:", "fix:"],
                }
            ]
        }

        mock_committer = MagicMock()
        mock_committer.date = datetime(2026, 2, 18, 8, 0, tzinfo=timezone.utc)

        mock_commit_data = MagicMock()
        mock_commit_data.message = "feat: add new Move module\n\nDetails here"
        mock_commit_data.committer = mock_committer

        mock_commit = MagicMock()
        mock_commit.commit = mock_commit_data
        mock_commit.sha = "abc123def456789012345678"
        mock_commit.html_url = "https://github.com/aptos-labs/aptos-core/commit/abc123"

        mock_repo = MagicMock()
        mock_repo.full_name = "aptos-labs/aptos-core"
        mock_repo.get_commits.return_value = [mock_commit]

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo

        from src.scrapers.github_repos import GitHubReposScraper

        scraper = GitHubReposScraper(client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        assert len(items) == 1
        item = items[0]
        assert item["id"] == "commit:aptos-labs/aptos-core:abc123def456"
        assert item["source_type"] == "commit"
        assert item["title"] == "feat: add new Move module"
        assert item["sha"] == "abc123def456789012345678"

    @patch("src.scrapers.github_repos.load_repos_config")
    @patch("src.scrapers.github_repos.wait_for_rate_limit")
    def test_scrape_commits_skips_non_matching(
        self, mock_wait, mock_config
    ):
        """Commits not matching any prefix are skipped."""
        mock_config.return_value = {
            "repos": [
                {
                    "owner": "aptos-labs",
                    "name": "aptos-core",
                    "track": ["commits"],
                    "commit_prefixes": ["feat:"],
                }
            ]
        }

        mock_committer = MagicMock()
        mock_committer.date = datetime(2026, 2, 18, 8, 0, tzinfo=timezone.utc)

        mock_commit_data = MagicMock()
        mock_commit_data.message = "chore: update deps"
        mock_commit_data.committer = mock_committer

        mock_commit = MagicMock()
        mock_commit.commit = mock_commit_data
        mock_commit.sha = "def456abc789"

        mock_repo = MagicMock()
        mock_repo.full_name = "aptos-labs/aptos-core"
        mock_repo.get_commits.return_value = [mock_commit]

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo

        from src.scrapers.github_repos import GitHubReposScraper

        scraper = GitHubReposScraper(client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        assert len(items) == 0

    @patch("src.scrapers.github_repos.load_repos_config")
    @patch("src.scrapers.github_repos.wait_for_rate_limit")
    def test_failed_repo_access_logs_and_continues(
        self, mock_wait, mock_config
    ):
        """If get_repo raises, the scraper logs and skips that repo."""
        mock_config.return_value = {
            "repos": [
                {
                    "owner": "aptos-labs",
                    "name": "nonexistent-repo",
                    "track": ["releases"],
                }
            ]
        }

        mock_client = MagicMock()
        mock_client.get_repo.side_effect = Exception("Not found")

        from src.scrapers.github_repos import GitHubReposScraper

        scraper = GitHubReposScraper(client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        assert items == []


# ---------------------------------------------------------------------------
# _parse_aip_frontmatter
# ---------------------------------------------------------------------------


class TestParseAIPFrontmatter:
    """Directly test the AIP YAML-like frontmatter parser."""

    def test_standard_frontmatter(self):
        content = """---
aip: 42
title: Token Standard V2
status: Accepted
author: dev@aptos.dev
---

# AIP-42: Token Standard V2

Body text here.
"""
        result = _parse_aip_frontmatter(content)
        assert result["aip"] == "42"
        assert result["title"] == "Token Standard V2"
        assert result["status"] == "Accepted"
        assert result["author"] == "dev@aptos.dev"

    def test_quoted_values_are_stripped(self):
        content = """---
title: "My Fancy AIP"
status: 'Draft'
---
"""
        result = _parse_aip_frontmatter(content)
        assert result["title"] == "My Fancy AIP"
        assert result["status"] == "Draft"

    def test_keys_are_lowercased(self):
        content = """---
Title: Something
STATUS: Ready
---
"""
        result = _parse_aip_frontmatter(content)
        assert "title" in result
        assert "status" in result
        assert result["title"] == "Something"
        assert result["status"] == "Ready"

    def test_no_frontmatter_returns_empty(self):
        content = "# Just a markdown file\n\nNo frontmatter here."
        result = _parse_aip_frontmatter(content)
        assert result == {}

    def test_empty_content_returns_empty(self):
        result = _parse_aip_frontmatter("")
        assert result == {}

    def test_frontmatter_with_colons_in_value(self):
        """Values containing colons are handled correctly (partition on first)."""
        content = """---
title: AIP-99: Fancy Feature: Extended
---
"""
        result = _parse_aip_frontmatter(content)
        assert result["title"] == "AIP-99: Fancy Feature: Extended"


# ---------------------------------------------------------------------------
# GitHubAIPsScraper
# ---------------------------------------------------------------------------


class TestGitHubAIPsScraper:
    """Test GitHubAIPsScraper with mocked GitHub and state."""

    @patch("src.scrapers.github_aips._save_state")
    @patch("src.scrapers.github_aips._load_state")
    @patch("src.scrapers.github_aips.load_sources_config")
    @patch("src.scrapers.github_aips.wait_for_rate_limit")
    def test_scrape_new_aip(
        self, mock_wait, mock_sources, mock_load_state, mock_save_state
    ):
        """A new AIP file is detected and included in results."""
        mock_sources.return_value = {
            "aips": {
                "owner": "aptos-foundation",
                "name": "AIPs",
                "path": "aips",
                "branch": "main",
            }
        }
        mock_load_state.return_value = {"known_aips": {}}

        frontmatter = (
            "---\naip: 77\ntitle: Gas Schedule V2\nstatus: Draft\n---\n"
            "# AIP-77\nBody."
        )
        mock_entry = MagicMock()
        mock_entry.name = "aip-77.md"
        mock_entry.sha = "sha_aip77_abc123"
        mock_entry.path = "aips/aip-77.md"
        mock_entry.decoded_content = frontmatter.encode("utf-8")

        mock_last_commit_data = MagicMock()
        mock_last_commit_data.committer.date = datetime(
            2026, 2, 20, 10, 0, tzinfo=timezone.utc
        )
        mock_last_commit = MagicMock()
        mock_last_commit.commit = mock_last_commit_data

        mock_commits = MagicMock()
        mock_commits.__getitem__ = MagicMock(return_value=mock_last_commit)

        mock_repo = MagicMock()
        mock_repo.full_name = "aptos-foundation/AIPs"
        mock_repo.get_contents.return_value = [mock_entry]
        mock_repo.get_commits.return_value = mock_commits

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo

        from src.scrapers.github_aips import GitHubAIPsScraper

        scraper = GitHubAIPsScraper(client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        assert len(items) == 1
        item = items[0]
        assert item["aip_number"] == 77
        assert item["title"] == "AIP-77: Gas Schedule V2"
        assert item["status"] == "Draft"
        assert item["is_new"] is True
        assert item["source_type"] == "aip"

    @patch("src.scrapers.github_aips._save_state")
    @patch("src.scrapers.github_aips._load_state")
    @patch("src.scrapers.github_aips.load_sources_config")
    @patch("src.scrapers.github_aips.wait_for_rate_limit")
    def test_scrape_unchanged_aip_is_skipped(
        self, mock_wait, mock_sources, mock_load_state, mock_save_state
    ):
        """An AIP whose SHA has not changed since last scrape is skipped."""
        mock_sources.return_value = {
            "aips": {
                "owner": "aptos-foundation",
                "name": "AIPs",
                "path": "aips",
                "branch": "main",
            }
        }
        mock_load_state.return_value = {
            "known_aips": {"77": "sha_unchanged"}
        }

        mock_entry = MagicMock()
        mock_entry.name = "aip-77.md"
        mock_entry.sha = "sha_unchanged"  # Same as known
        mock_entry.path = "aips/aip-77.md"

        mock_repo = MagicMock()
        mock_repo.full_name = "aptos-foundation/AIPs"
        mock_repo.get_contents.return_value = [mock_entry]

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo

        from src.scrapers.github_aips import GitHubAIPsScraper

        scraper = GitHubAIPsScraper(client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        assert items == []


# ---------------------------------------------------------------------------
# WebContentScraper — RSS feed parsing
# ---------------------------------------------------------------------------


class TestWebContentScraper:
    """Test WebContentScraper with mocked HTTP responses."""

    RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Aptos Blog</title>
    <item>
      <title>Move 2.0 Released</title>
      <link>https://aptoslabs.com/blog/move-2</link>
      <pubDate>Tue, 17 Feb 2026 12:00:00 GMT</pubDate>
      <description>&lt;p&gt;Exciting new features in Move 2.0.&lt;/p&gt;</description>
    </item>
    <item>
      <title>Old Post</title>
      <link>https://aptoslabs.com/blog/old</link>
      <pubDate>Mon, 05 Jan 2026 12:00:00 GMT</pubDate>
      <description>This is old.</description>
    </item>
  </channel>
</rss>"""

    @patch("src.scrapers.web_content.load_sources_config")
    @patch("src.scrapers.web_content.httpx.Client")
    def test_scrape_blog_rss_parses_entries(
        self, mock_httpx_client_cls, mock_config
    ):
        """Blog RSS entries within range are parsed into items."""
        mock_config.return_value = {
            "blog": {"url": "https://aptoslabs.com/blog/rss"},
            "forum": {},
        }

        mock_response = MagicMock()
        mock_response.text = self.RSS_FEED
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_httpx_client_cls.return_value = mock_client_instance

        from src.scrapers.web_content import WebContentScraper

        scraper = WebContentScraper()
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        # Only the February post should match
        assert len(items) == 1
        item = items[0]
        assert item["source_type"] == "blog"
        assert item["title"] == "Move 2.0 Released"
        assert item["url"] == "https://aptoslabs.com/blog/move-2"
        assert item["date"] == "2026-02-17"
        assert "Move 2.0" in item["body"]

    @patch("src.scrapers.web_content.load_sources_config")
    @patch("src.scrapers.web_content.httpx.Client")
    def test_scrape_blog_rss_failure_returns_empty(
        self, mock_httpx_client_cls, mock_config
    ):
        """If the RSS fetch fails and there is no fallback, return empty."""
        mock_config.return_value = {
            "blog": {"url": "https://aptoslabs.com/blog/rss"},
            "forum": {},
        }

        mock_client_instance = MagicMock()
        mock_client_instance.get.side_effect = Exception("Connection refused")
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_httpx_client_cls.return_value = mock_client_instance

        from src.scrapers.web_content import WebContentScraper

        scraper = WebContentScraper()
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        assert items == []

    @patch("src.scrapers.web_content.load_sources_config")
    @patch("src.scrapers.web_content.httpx.Client")
    def test_scrape_forum_parses_topics(
        self, mock_httpx_client_cls, mock_config
    ):
        """Forum topics within range and above thresholds are collected."""
        mock_config.return_value = {
            "blog": {},
            "forum": {
                "base_url": "https://forum.aptosfoundation.org",
                "min_likes": 2,
                "min_replies": 1,
                "categories": [
                    {"slug": "dev-general", "id": 5},
                ],
            },
        }

        forum_response_data = {
            "topic_list": {
                "topics": [
                    {
                        "id": 101,
                        "title": "How to use new indexer?",
                        "slug": "how-to-use-new-indexer",
                        "created_at": "2026-02-18T14:30:00Z",
                        "like_count": 5,
                        "posts_count": 4,  # 3 replies (posts_count - 1)
                    },
                    {
                        "id": 102,
                        "title": "Low engagement post",
                        "slug": "low-engagement",
                        "created_at": "2026-02-19T10:00:00Z",
                        "like_count": 0,  # Below min_likes=2
                        "posts_count": 1,
                    },
                ]
            }
        }

        mock_response = MagicMock()
        mock_response.json.return_value = forum_response_data
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_httpx_client_cls.return_value = mock_client_instance

        from src.scrapers.web_content import WebContentScraper

        scraper = WebContentScraper()
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        # Only the high-engagement topic should pass filters
        assert len(items) == 1
        item = items[0]
        assert item["id"] == "forum:101"
        assert item["source_type"] == "forum"
        assert item["title"] == "How to use new indexer?"
        assert item["likes"] == 5
        assert item["replies"] == 3
        assert item["category"] == "dev-general"

    @patch("src.scrapers.web_content.load_sources_config")
    def test_scrape_with_no_blog_or_forum_config(self, mock_config):
        """Scraper returns empty when blog/forum URLs are not configured."""
        mock_config.return_value = {
            "blog": {},
            "forum": {},
        }

        from src.scrapers.web_content import WebContentScraper

        scraper = WebContentScraper()
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))
        assert items == []
