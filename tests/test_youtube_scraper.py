"""Tests for the YouTube scraper."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.scrapers.youtube import YouTubeScraper, _parse_iso8601_duration


# ---------------------------------------------------------------------------
# _parse_iso8601_duration
# ---------------------------------------------------------------------------


class TestParseISO8601Duration:
    def test_minutes_and_seconds(self):
        assert _parse_iso8601_duration("PT5M30S") == 330.0

    def test_hours_minutes_seconds(self):
        assert _parse_iso8601_duration("PT1H2M3S") == 3723.0

    def test_seconds_only(self):
        assert _parse_iso8601_duration("PT45S") == 45.0

    def test_minutes_only(self):
        assert _parse_iso8601_duration("PT10M") == 600.0

    def test_zero_duration(self):
        assert _parse_iso8601_duration("PT0S") == 0.0

    def test_invalid_string(self):
        assert _parse_iso8601_duration("invalid") == 0.0

    def test_empty_string(self):
        assert _parse_iso8601_duration("") == 0.0


# ---------------------------------------------------------------------------
# YouTubeScraper
# ---------------------------------------------------------------------------


class TestYouTubeScraper:
    """Test YouTubeScraper with mocked HTTP responses."""

    CHANNEL_RESPONSE = {
        "items": [
            {
                "contentDetails": {
                    "relatedPlaylists": {"uploads": "UU_uploads_123"}
                }
            }
        ]
    }

    PLAYLIST_RESPONSE = {
        "items": [
            {
                "snippet": {
                    "publishedAt": "2026-02-15T10:00:00Z",
                    "resourceId": {"videoId": "vid_abc123"},
                }
            },
            {
                "snippet": {
                    "publishedAt": "2026-02-10T08:00:00Z",
                    "resourceId": {"videoId": "vid_def456"},
                }
            },
            {
                # Short video — will be filtered by duration
                "snippet": {
                    "publishedAt": "2026-02-12T12:00:00Z",
                    "resourceId": {"videoId": "vid_short"},
                }
            },
        ]
    }

    VIDEO_DETAILS_RESPONSE = {
        "items": [
            {
                "id": "vid_abc123",
                "snippet": {
                    "title": "Aptos Move Tutorial",
                    "description": "Learn Move programming on Aptos.",
                    "publishedAt": "2026-02-15T10:00:00Z",
                },
                "contentDetails": {"duration": "PT15M30S"},
            },
            {
                "id": "vid_def456",
                "snippet": {
                    "title": "Aptos Indexer Deep Dive",
                    "description": "Understanding the Aptos indexer.",
                    "publishedAt": "2026-02-10T08:00:00Z",
                },
                "contentDetails": {"duration": "PT45M0S"},
            },
            {
                "id": "vid_short",
                "snippet": {
                    "title": "Quick Tip",
                    "description": "A short tip.",
                    "publishedAt": "2026-02-12T12:00:00Z",
                },
                "contentDetails": {"duration": "PT30S"},  # < 60s
            },
        ]
    }

    def _mock_client(self, responses: dict[str, dict] | None = None):
        """Create a mock httpx.Client that returns canned responses by URL path."""
        if responses is None:
            responses = {
                "/channels": self.CHANNEL_RESPONSE,
                "/playlistItems": self.PLAYLIST_RESPONSE,
                "/videos": self.VIDEO_DETAILS_RESPONSE,
            }

        mock_client = MagicMock()

        def fake_get(url, **kwargs):
            resp = MagicMock()
            for path, data in responses.items():
                if path in url:
                    resp.json.return_value = data
                    resp.raise_for_status = MagicMock()
                    return resp
            resp.json.return_value = {"items": []}
            resp.raise_for_status = MagicMock()
            return resp

        mock_client.get = fake_get
        return mock_client

    @patch("src.scrapers.youtube.load_sources_config")
    def test_scrape_returns_videos_in_range(self, mock_config):
        mock_config.return_value = {
            "youtube": {
                "channels": [
                    {"name": "Aptos Developers", "channel_id": "UC_test123"},
                ],
                "min_duration_seconds": 60,
            }
        }

        http_client = self._mock_client()
        scraper = YouTubeScraper(api_key="test-key", http_client=http_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        # Short video should be filtered out
        assert len(items) == 2
        titles = {item["title"] for item in items}
        assert "Aptos Move Tutorial" in titles
        assert "Aptos Indexer Deep Dive" in titles
        assert "Quick Tip" not in titles

    @patch("src.scrapers.youtube.load_sources_config")
    def test_scrape_item_schema(self, mock_config):
        mock_config.return_value = {
            "youtube": {
                "channels": [
                    {"name": "Aptos Developers", "channel_id": "UC_test123"},
                ],
                "min_duration_seconds": 60,
            }
        }

        http_client = self._mock_client()
        scraper = YouTubeScraper(api_key="test-key", http_client=http_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        item = next(i for i in items if i["title"] == "Aptos Move Tutorial")
        assert item["id"] == "youtube:vid_abc123"
        assert item["source_type"] == "youtube"
        assert item["url"] == "https://www.youtube.com/watch?v=vid_abc123"
        assert item["date"] == "2026-02-15"
        assert item["repo"] == "youtube/aptos-developers"
        assert "Learn Move" in item["body"]

    @patch("src.scrapers.youtube.load_sources_config")
    def test_scrape_skips_without_api_key(self, mock_config):
        mock_config.return_value = {
            "youtube": {
                "channels": [
                    {"name": "Aptos Developers", "channel_id": "UC_test123"},
                ],
            }
        }

        scraper = YouTubeScraper(api_key="", http_client=self._mock_client())
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))
        assert items == []

    @patch("src.scrapers.youtube.load_sources_config")
    def test_scrape_no_channels_configured(self, mock_config):
        mock_config.return_value = {"youtube": {"channels": []}}

        scraper = YouTubeScraper(api_key="test-key", http_client=self._mock_client())
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))
        assert items == []

    @patch("src.scrapers.youtube.load_sources_config")
    def test_scrape_filters_by_date_range(self, mock_config):
        mock_config.return_value = {
            "youtube": {
                "channels": [
                    {"name": "Aptos Developers", "channel_id": "UC_test123"},
                ],
                "min_duration_seconds": 60,
            }
        }

        http_client = self._mock_client()
        scraper = YouTubeScraper(api_key="test-key", http_client=http_client)
        # Narrow range that only includes the Feb 15 video
        items = scraper.scrape(since=date(2026, 2, 14), until=date(2026, 2, 16))

        assert len(items) == 1
        assert items[0]["title"] == "Aptos Move Tutorial"

    @patch("src.scrapers.youtube.load_sources_config")
    def test_scrape_handles_api_error_gracefully(self, mock_config):
        mock_config.return_value = {
            "youtube": {
                "channels": [
                    {"name": "Aptos Developers", "channel_id": "UC_test123"},
                ],
            }
        }

        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("API error")

        scraper = YouTubeScraper(api_key="test-key", http_client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))
        assert items == []

    @patch("src.scrapers.youtube.load_sources_config")
    def test_scrape_channel_not_found(self, mock_config):
        mock_config.return_value = {
            "youtube": {
                "channels": [
                    {"name": "Missing Channel", "channel_id": "UC_missing"},
                ],
            }
        }

        http_client = self._mock_client(
            responses={"/channels": {"items": []}}
        )
        scraper = YouTubeScraper(api_key="test-key", http_client=http_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))
        assert items == []
