"""Tests for the changelog renderer module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.generator.changelog_renderer import (
    group_by_repo,
    _build_stats,
    render_changelog_markdown,
    render_changelog_html,
    render_changelog_index,
)


MOCK_NEWSLETTER_CONFIG = {
    "sections": [],
    "branding": {
        "title": "Aptos Developer Monthly",
        "tagline": "Your monthly digest of Aptos ecosystem updates",
        "footer": "Published by Aptos Labs DevRel",
        "color_primary": "#00D4AA",
        "color_bg": "#0B1221",
        "color_text": "#E8E8E8",
        "color_muted": "#8B95A5",
        "logo_url": "",
        "changelog_base_url": "https://example.com/changelogs",
    },
}

SAMPLE_ITEMS = [
    {
        "id": "release:aptos-labs/aptos-core:v1.8.0",
        "source_type": "release",
        "title": "aptos-core v1.8.0",
        "body": "Release notes",
        "body_full": "Full release notes with lots of detail",
        "url": "https://github.com/aptos-labs/aptos-core/releases/v1.8.0",
        "date": "2026-02-20",
        "repo": "aptos-labs/aptos-core",
        "tag": "v1.8.0",
    },
    {
        "id": "pr:aptos-labs/aptos-core:#42",
        "source_type": "pr",
        "title": "Improve consensus throughput",
        "body": "PR description",
        "url": "https://github.com/aptos-labs/aptos-core/pull/42",
        "date": "2026-02-18",
        "repo": "aptos-labs/aptos-core",
        "changed_files": 5,
        "additions": 100,
        "deletions": 20,
    },
    {
        "id": "release:aptos-labs/aptos-ts-sdk:v2.1.0",
        "source_type": "release",
        "title": "aptos-ts-sdk v2.1.0",
        "body": "SDK release",
        "body_full": "Full SDK release notes",
        "url": "https://github.com/aptos-labs/aptos-ts-sdk/releases/v2.1.0",
        "date": "2026-02-15",
        "repo": "aptos-labs/aptos-ts-sdk",
        "tag": "v2.1.0",
    },
    {
        "id": "commit:aptos-labs/aptos-core:abc123def456",
        "source_type": "commit",
        "title": "feat: add new Move module",
        "url": "https://github.com/aptos-labs/aptos-core/commit/abc123",
        "date": "2026-02-16",
        "repo": "aptos-labs/aptos-core",
        "sha": "abc123def456789012345678",
    },
    {
        "id": "changelog:aptos-labs/aptos-ts-sdk:2.1.0",
        "source_type": "changelog_entry",
        "title": "aptos-ts-sdk 2.1.0",
        "body": "Changelog content",
        "body_full": "Full changelog content",
        "url": "https://github.com/aptos-labs/aptos-ts-sdk/blob/main/CHANGELOG.md",
        "date": "2026-02-14",
        "repo": "aptos-labs/aptos-ts-sdk",
        "version": "2.1.0",
    },
]


class TestGroupByRepo:
    def test_groups_items_by_repo(self):
        grouped = group_by_repo(SAMPLE_ITEMS)
        assert "aptos-labs/aptos-core" in grouped
        assert "aptos-labs/aptos-ts-sdk" in grouped

    def test_repos_sorted_alphabetically(self):
        grouped = group_by_repo(SAMPLE_ITEMS)
        keys = list(grouped.keys())
        assert keys == sorted(keys)

    def test_items_sorted_by_date_descending(self):
        grouped = group_by_repo(SAMPLE_ITEMS)
        core_items = grouped["aptos-labs/aptos-core"]
        dates = [item["date"] for item in core_items]
        assert dates == sorted(dates, reverse=True)

    def test_correct_item_counts(self):
        grouped = group_by_repo(SAMPLE_ITEMS)
        assert len(grouped["aptos-labs/aptos-core"]) == 3
        assert len(grouped["aptos-labs/aptos-ts-sdk"]) == 2

    def test_empty_input(self):
        assert group_by_repo([]) == {}


class TestBuildStats:
    def test_counts_all_types(self):
        stats = _build_stats(SAMPLE_ITEMS)
        assert stats["total"] == 5
        assert stats["releases"] == 2
        assert stats["prs"] == 1
        assert stats["commits"] == 1
        assert stats["changelog_entries"] == 1
        assert stats["repos_active"] == 2

    def test_empty_items(self):
        stats = _build_stats([])
        assert stats["total"] == 0
        assert stats["releases"] == 0
        assert stats["repos_active"] == 0


class TestRenderChangelogMarkdown:
    def test_renders_markdown_with_title(self):
        md = render_changelog_markdown(SAMPLE_ITEMS, "2026-02")
        assert "Aptos Ecosystem Changelog — 2026-02" in md

    def test_renders_stats_table(self):
        md = render_changelog_markdown(SAMPLE_ITEMS, "2026-02")
        assert "Total items" in md
        assert "Releases" in md
        assert "PRs merged" in md

    def test_renders_repo_sections(self):
        md = render_changelog_markdown(SAMPLE_ITEMS, "2026-02")
        assert "## aptos-labs/aptos-core" in md
        assert "## aptos-labs/aptos-ts-sdk" in md

    def test_renders_release_details(self):
        md = render_changelog_markdown(SAMPLE_ITEMS, "2026-02")
        assert "aptos-core v1.8.0" in md
        assert "Full release notes with lots of detail" in md

    def test_renders_pr_table(self):
        md = render_changelog_markdown(SAMPLE_ITEMS, "2026-02")
        assert "Improve consensus throughput" in md

    def test_renders_commit_list(self):
        md = render_changelog_markdown(SAMPLE_ITEMS, "2026-02")
        assert "feat: add new Move module" in md

    def test_renders_changelog_entries(self):
        md = render_changelog_markdown(SAMPLE_ITEMS, "2026-02")
        assert "Changelog Entries" in md
        assert "Full changelog content" in md


class TestRenderChangelogHtml:
    @patch(
        "src.generator.changelog_renderer.load_newsletter_config",
        return_value=MOCK_NEWSLETTER_CONFIG,
    )
    def test_renders_html_page(self, mock_config):
        html = render_changelog_html(SAMPLE_ITEMS, "2026-02")
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    @patch(
        "src.generator.changelog_renderer.load_newsletter_config",
        return_value=MOCK_NEWSLETTER_CONFIG,
    )
    def test_contains_stats(self, mock_config):
        html = render_changelog_html(SAMPLE_ITEMS, "2026-02")
        assert "Total Items" in html

    @patch(
        "src.generator.changelog_renderer.load_newsletter_config",
        return_value=MOCK_NEWSLETTER_CONFIG,
    )
    def test_contains_repo_sections(self, mock_config):
        html = render_changelog_html(SAMPLE_ITEMS, "2026-02")
        assert "aptos-labs/aptos-core" in html
        assert "aptos-labs/aptos-ts-sdk" in html

    @patch(
        "src.generator.changelog_renderer.load_newsletter_config",
        return_value=MOCK_NEWSLETTER_CONFIG,
    )
    def test_contains_branding_colors(self, mock_config):
        html = render_changelog_html(SAMPLE_ITEMS, "2026-02")
        assert "#00D4AA" in html
        assert "#0B1221" in html

    @patch(
        "src.generator.changelog_renderer.load_newsletter_config",
        return_value=MOCK_NEWSLETTER_CONFIG,
    )
    def test_sidebar_has_repo_links(self, mock_config):
        html = render_changelog_html(SAMPLE_ITEMS, "2026-02")
        assert "sidebar" in html
        assert "aptos-core" in html


class TestRenderChangelogIndex:
    @patch(
        "src.generator.changelog_renderer.load_newsletter_config",
        return_value=MOCK_NEWSLETTER_CONFIG,
    )
    def test_renders_index_with_months(self, mock_config):
        html = render_changelog_index(["2026-01", "2026-02"])
        assert "<!DOCTYPE html>" in html
        assert "2026-02" in html
        assert "2026-01" in html

    @patch(
        "src.generator.changelog_renderer.load_newsletter_config",
        return_value=MOCK_NEWSLETTER_CONFIG,
    )
    def test_months_sorted_descending(self, mock_config):
        html = render_changelog_index(["2026-01", "2026-03", "2026-02"])
        pos_03 = html.index("2026-03")
        pos_02 = html.index("2026-02")
        pos_01 = html.index("2026-01")
        assert pos_03 < pos_02 < pos_01

    @patch(
        "src.generator.changelog_renderer.load_newsletter_config",
        return_value=MOCK_NEWSLETTER_CONFIG,
    )
    def test_contains_branding(self, mock_config):
        html = render_changelog_index(["2026-01"])
        assert "Aptos Developer Monthly" in html
        assert "Changelog Archive" in html

    @patch(
        "src.generator.changelog_renderer.load_newsletter_config",
        return_value=MOCK_NEWSLETTER_CONFIG,
    )
    def test_empty_months(self, mock_config):
        html = render_changelog_index([])
        assert "<!DOCTYPE html>" in html
