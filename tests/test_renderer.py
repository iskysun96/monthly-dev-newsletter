"""Tests for the renderer module — Markdown and HTML newsletter generation."""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

MOCK_NEWSLETTER_CONFIG = {
    "sections": [
        {"id": "releases", "title": "Releases", "priority": 1, "rules": []},
        {"id": "aips", "title": "Governance & AIPs", "priority": 2, "rules": []},
        {"id": "community", "title": "Community", "priority": 3, "rules": []},
    ],
    "branding": {
        "title": "Aptos Developer Monthly",
        "tagline": "Your monthly digest of Aptos ecosystem updates",
        "footer": "Published by Aptos Labs DevRel",
        "color_primary": "#00D4AA",
        "color_bg": "#0B1221",
        "color_text": "#E8E8E8",
        "color_muted": "#8B95A5",
        "logo_url": "",
    },
}

SAMPLE_SUMMARIES = {
    "intro": "This month saw major releases and governance activity.",
    "sections": {
        "releases": "Two new releases shipped with performance improvements.",
        "aips": "Three AIPs were proposed covering gas and storage changes.",
    },
}

SAMPLE_CATEGORIZED = {
    "releases": [
        {
            "id": "r1",
            "title": "aptos-core v1.8.0",
            "url": "https://github.com/aptos-labs/aptos-core/releases/v1.8.0",
            "repo": "aptos-labs/aptos-core",
            "date": "2026-02-20",
        },
        {
            "id": "r2",
            "title": "aptos-ts-sdk v2.1.0",
            "url": "https://github.com/aptos-labs/aptos-ts-sdk/releases/v2.1.0",
            "repo": "aptos-labs/aptos-ts-sdk",
            "date": "2026-02-18",
        },
    ],
    "aips": [
        {
            "id": "a1",
            "title": "AIP-77: Gas Schedule V2",
            "url": "https://github.com/aptos-foundation/AIPs/blob/main/aips/aip-77.md",
            "repo": "aptos-foundation/AIPs",
            "date": "2026-02-15",
        },
    ],
    "community": [],
}

MONTH_YEAR = "February 2026"


# ---------------------------------------------------------------------------
# _build_context
# ---------------------------------------------------------------------------


class TestBuildContext:
    """Test the _build_context helper."""

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_builds_expected_structure(self, mock_config):
        from src.generator.renderer import _build_context

        ctx = _build_context(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert ctx["month_year"] == MONTH_YEAR
        assert ctx["intro"] == SAMPLE_SUMMARIES["intro"]
        assert ctx["branding"]["title"] == "Aptos Developer Monthly"
        assert ctx["branding"]["tagline"] == "Your monthly digest of Aptos ecosystem updates"

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_sections_populated_with_items(self, mock_config):
        from src.generator.renderer import _build_context

        ctx = _build_context(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        section_ids = [s["id"] for s in ctx["sections"]]
        # 'releases' has items + summary, 'aips' has items + summary
        assert "releases" in section_ids
        assert "aips" in section_ids

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_empty_sections_without_summary_excluded(self, mock_config):
        """Sections with no items and no summary text are excluded from context."""
        from src.generator.renderer import _build_context

        ctx = _build_context(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        section_ids = [s["id"] for s in ctx["sections"]]
        # 'community' has no items and no summary, so it should be excluded
        assert "community" not in section_ids

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_section_title_from_config(self, mock_config):
        from src.generator.renderer import _build_context

        ctx = _build_context(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        releases_section = next(s for s in ctx["sections"] if s["id"] == "releases")
        assert releases_section["title"] == "Releases"

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_section_summary_populated(self, mock_config):
        from src.generator.renderer import _build_context

        ctx = _build_context(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        releases_section = next(s for s in ctx["sections"] if s["id"] == "releases")
        assert "performance improvements" in releases_section["summary"]

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_section_items_match_categorized(self, mock_config):
        from src.generator.renderer import _build_context

        ctx = _build_context(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        releases_section = next(s for s in ctx["sections"] if s["id"] == "releases")
        assert len(releases_section["entries"]) == 2
        assert releases_section["entries"][0]["id"] == "r1"

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_missing_intro_defaults_to_empty(self, mock_config):
        from src.generator.renderer import _build_context

        summaries_no_intro = {"sections": {"releases": "Summary text"}}
        ctx = _build_context(summaries_no_intro, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert ctx["intro"] == ""


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    """Test Markdown output via the real Jinja2 template."""

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_produces_valid_markdown(self, mock_config):
        from src.generator.renderer import render_markdown

        md = render_markdown(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        # Title line
        assert "# Aptos Developer Monthly" in md
        assert "February 2026" in md

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_contains_section_headings(self, mock_config):
        from src.generator.renderer import render_markdown

        md = render_markdown(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert "## Releases" in md
        assert "## Governance & AIPs" in md

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_contains_item_titles(self, mock_config):
        from src.generator.renderer import render_markdown

        md = render_markdown(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert "aptos-core v1.8.0" in md
        assert "aptos-ts-sdk v2.1.0" in md
        assert "AIP-77: Gas Schedule V2" in md

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_contains_item_links(self, mock_config):
        from src.generator.renderer import render_markdown

        md = render_markdown(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert "https://github.com/aptos-labs/aptos-core/releases/v1.8.0" in md

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_contains_repo_names(self, mock_config):
        from src.generator.renderer import render_markdown

        md = render_markdown(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert "aptos-labs/aptos-core" in md

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_contains_intro_text(self, mock_config):
        from src.generator.renderer import render_markdown

        md = render_markdown(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert "major releases and governance activity" in md

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_contains_section_summaries(self, mock_config):
        from src.generator.renderer import render_markdown

        md = render_markdown(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert "Two new releases shipped" in md
        assert "Three AIPs were proposed" in md

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_contains_footer(self, mock_config):
        from src.generator.renderer import render_markdown

        md = render_markdown(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert "Published by Aptos Labs DevRel" in md

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_empty_sections_omitted_from_output(self, mock_config):
        from src.generator.renderer import render_markdown

        md = render_markdown(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        # 'community' section had no items and no summary, should not appear
        assert "## Community" not in md


# ---------------------------------------------------------------------------
# render_html
# ---------------------------------------------------------------------------


class TestRenderHtml:
    """Test HTML output via the real Jinja2 template."""

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_produces_valid_html(self, mock_config):
        from src.generator.renderer import render_html

        html = render_html(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert "<!DOCTYPE" in html or "<html" in html
        assert "</html>" in html

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_contains_branding_title(self, mock_config):
        from src.generator.renderer import render_html

        html = render_html(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert "Aptos Developer Monthly" in html

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_contains_month_year(self, mock_config):
        from src.generator.renderer import render_html

        html = render_html(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert "February 2026" in html

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_contains_section_headings(self, mock_config):
        from src.generator.renderer import render_html

        html = render_html(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert "Releases" in html
        assert "Governance &amp; AIPs" in html or "Governance & AIPs" in html

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_contains_item_links(self, mock_config):
        from src.generator.renderer import render_html

        html = render_html(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert 'href="https://github.com/aptos-labs/aptos-core/releases/v1.8.0"' in html

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_contains_item_titles(self, mock_config):
        from src.generator.renderer import render_html

        html = render_html(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert "aptos-core v1.8.0" in html
        assert "AIP-77: Gas Schedule V2" in html

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_contains_footer_text(self, mock_config):
        from src.generator.renderer import render_html

        html = render_html(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert "Published by Aptos Labs DevRel" in html

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_has_inlined_styles(self, mock_config):
        """premailer should inline CSS, so style attributes should appear on elements."""
        from src.generator.renderer import render_html

        html = render_html(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        # premailer inlines styles into style="" attributes
        assert 'style="' in html

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_contains_intro_text(self, mock_config):
        from src.generator.renderer import render_html

        html = render_html(SAMPLE_SUMMARIES, SAMPLE_CATEGORIZED, MONTH_YEAR)

        assert "major releases and governance activity" in html


# ---------------------------------------------------------------------------
# Metadata line in Markdown output
# ---------------------------------------------------------------------------


class TestMarkdownMetadata:
    """Verify that the metadata line (source_type, repo, date) appears in Markdown output."""

    CATEGORIZED_WITH_METADATA = {
        "releases": [
            {
                "id": "r1",
                "title": "aptos-core v1.8.0",
                "url": "https://github.com/aptos-labs/aptos-core/releases/v1.8.0",
                "repo": "aptos-labs/aptos-core",
                "date": "2026-02-20",
                "source_type": "release",
            },
        ],
        "aips": [
            {
                "id": "a1",
                "title": "AIP-77: Gas Schedule V2",
                "url": "https://github.com/aptos-foundation/AIPs/blob/main/aips/aip-77.md",
                "repo": "aptos-foundation/AIPs",
                "date": "2026-02-15",
                "source_type": "aip",
            },
        ],
        "community": [],
    }

    SUMMARIES_FOR_METADATA = {
        "intro": "This month saw updates.",
        "sections": {
            "releases": "Release notes.",
            "aips": "AIP updates.",
        },
    }

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_metadata_line_contains_source_type(self, mock_config):
        from src.generator.renderer import render_markdown

        md = render_markdown(
            self.SUMMARIES_FOR_METADATA, self.CATEGORIZED_WITH_METADATA, MONTH_YEAR
        )

        assert "_release" in md
        assert "_aip" in md

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_metadata_line_contains_date(self, mock_config):
        from src.generator.renderer import render_markdown

        md = render_markdown(
            self.SUMMARIES_FOR_METADATA, self.CATEGORIZED_WITH_METADATA, MONTH_YEAR
        )

        assert "2026-02-20" in md
        assert "2026-02-15" in md

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_metadata_line_contains_repo(self, mock_config):
        from src.generator.renderer import render_markdown

        md = render_markdown(
            self.SUMMARIES_FOR_METADATA, self.CATEGORIZED_WITH_METADATA, MONTH_YEAR
        )

        # Repo appears both in the item line and in the metadata line
        assert "aptos-labs/aptos-core" in md
        assert "aptos-foundation/AIPs" in md

    @patch("src.generator.renderer.load_newsletter_config", return_value=MOCK_NEWSLETTER_CONFIG)
    def test_item_without_source_type_shows_default(self, mock_config):
        from src.generator.renderer import render_markdown

        categorized = {
            "releases": [
                {
                    "id": "r1",
                    "title": "Some release",
                    "url": "https://example.com",
                    "repo": "aptos-labs/aptos-core",
                    "date": "2026-02-20",
                    # no source_type key
                },
            ],
            "aips": [],
            "community": [],
        }
        summaries = {
            "intro": "Intro.",
            "sections": {"releases": "Summary."},
        }

        md = render_markdown(summaries, categorized, MONTH_YEAR)

        # Should fall back to "item" default
        assert "_item" in md
