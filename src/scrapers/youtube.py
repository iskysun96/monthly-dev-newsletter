"""Scraper for YouTube channel videos using YouTube Data API v3."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any

import httpx

from src.scrapers.base import BaseScraper
from src.utils.config_loader import load_sources_config

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 30.0
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeScraper(BaseScraper):
    name = "youtube"

    def __init__(self, api_key: str | None = None, http_client: httpx.Client | None = None):
        self.config = load_sources_config().get("youtube", {})
        self.api_key = api_key or os.environ.get("YOUTUBE_API_KEY", "")
        self._http_client = http_client

    def scrape(self, since: date, until: date) -> list[dict[str, Any]]:
        if not self.api_key:
            logger.warning("YOUTUBE_API_KEY not set, skipping YouTube scraper")
            return []

        channels = self.config.get("channels", [])
        if not channels:
            logger.info("No YouTube channels configured")
            return []

        min_duration = self.config.get("min_duration_seconds", 60)
        items: list[dict[str, Any]] = []

        for channel_cfg in channels:
            channel_name = channel_cfg.get("name", "Unknown")
            channel_id = channel_cfg.get("channel_id", "")
            if not channel_id:
                continue
            try:
                channel_items = self._scrape_channel(
                    channel_id, channel_name, since, until, min_duration
                )
                items.extend(channel_items)
            except Exception:
                logger.exception("YouTube scraper failed for channel %s", channel_name)

        return items

    def _get_client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        return httpx.Client(timeout=HTTP_TIMEOUT)

    def _scrape_channel(
        self,
        channel_id: str,
        channel_name: str,
        since: date,
        until: date,
        min_duration: int,
    ) -> list[dict[str, Any]]:
        uploads_playlist_id = self._get_uploads_playlist(channel_id)
        if not uploads_playlist_id:
            return []

        video_ids = self._get_playlist_video_ids(
            uploads_playlist_id, since, until
        )
        if not video_ids:
            return []

        videos = self._get_video_details(video_ids)
        items: list[dict[str, Any]] = []

        for video in videos:
            duration_seconds = _parse_iso8601_duration(
                video.get("contentDetails", {}).get("duration", "PT0S")
            )
            if duration_seconds < min_duration:
                logger.debug(
                    "Skipping short video (%.0fs): %s",
                    duration_seconds,
                    video.get("snippet", {}).get("title"),
                )
                continue

            snippet = video.get("snippet", {})
            video_id = video["id"]
            published_str = snippet.get("publishedAt", "")
            try:
                published = datetime.fromisoformat(
                    published_str.replace("Z", "+00:00")
                ).date()
            except (ValueError, AttributeError):
                continue

            if published < since or published > until:
                continue

            title = snippet.get("title", "Untitled")
            description = snippet.get("description", "")[:500]

            items.append(
                {
                    "id": f"youtube:{video_id}",
                    "source_type": "youtube",
                    "title": title,
                    "body": description,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "date": published.isoformat(),
                    "repo": f"youtube/{channel_name.lower().replace(' ', '-')}",
                }
            )

        return items

    def _get_uploads_playlist(self, channel_id: str) -> str:
        """Get the uploads playlist ID for a channel."""
        client = self._get_client()
        try:
            resp = client.get(
                f"{YOUTUBE_API_BASE}/channels",
                params={
                    "part": "contentDetails",
                    "id": channel_id,
                    "key": self.api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            if not items:
                logger.warning("Channel %s not found", channel_id)
                return ""
            return (
                items[0]
                .get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads", "")
            )
        except Exception:
            logger.exception("Failed to get uploads playlist for %s", channel_id)
            return ""
        finally:
            if self._http_client is None:
                client.close()

    def _get_playlist_video_ids(
        self, playlist_id: str, since: date, until: date
    ) -> list[str]:
        """Fetch video IDs from a playlist, filtered by date."""
        client = self._get_client()
        video_ids: list[str] = []
        page_token: str | None = None

        try:
            while True:
                params: dict[str, Any] = {
                    "part": "snippet",
                    "playlistId": playlist_id,
                    "maxResults": 50,
                    "key": self.api_key,
                }
                if page_token:
                    params["pageToken"] = page_token

                resp = client.get(
                    f"{YOUTUBE_API_BASE}/playlistItems", params=params
                )
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("items", []):
                    snippet = item.get("snippet", {})
                    published_str = snippet.get("publishedAt", "")
                    try:
                        published = datetime.fromisoformat(
                            published_str.replace("Z", "+00:00")
                        ).date()
                    except (ValueError, AttributeError):
                        continue

                    if published < since:
                        # Playlist is in reverse chronological order
                        return video_ids
                    if published > until:
                        continue

                    video_id = snippet.get("resourceId", {}).get("videoId", "")
                    if video_id:
                        video_ids.append(video_id)

                page_token = data.get("nextPageToken")
                if not page_token:
                    break
        except Exception:
            logger.exception("Failed to list playlist items for %s", playlist_id)
        finally:
            if self._http_client is None:
                client.close()

        return video_ids

    def _get_video_details(self, video_ids: list[str]) -> list[dict[str, Any]]:
        """Fetch video details (snippet + contentDetails) for a batch of IDs."""
        client = self._get_client()
        videos: list[dict[str, Any]] = []

        try:
            # YouTube API allows up to 50 IDs per request
            for i in range(0, len(video_ids), 50):
                batch = video_ids[i : i + 50]
                resp = client.get(
                    f"{YOUTUBE_API_BASE}/videos",
                    params={
                        "part": "snippet,contentDetails",
                        "id": ",".join(batch),
                        "key": self.api_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                videos.extend(data.get("items", []))
        except Exception:
            logger.exception("Failed to get video details")
        finally:
            if self._http_client is None:
                client.close()

        return videos


def _parse_iso8601_duration(duration: str) -> float:
    """Parse an ISO 8601 duration string (e.g. PT1H2M3S) to seconds."""
    import re

    match = re.match(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration
    )
    if not match:
        return 0.0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds
