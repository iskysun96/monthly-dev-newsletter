"""Scraper for blog (RSS) and Discourse forum content."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import feedparser
import httpx
from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper
from src.utils.config_loader import load_sources_config

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 30.0


class WebContentScraper(BaseScraper):
    name = "web-content"

    def __init__(self):
        self.config = load_sources_config()

    def scrape(self, since: date, until: date) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        items.extend(self._scrape_all_blogs(since, until))
        items.extend(self._scrape_forum(since, until))
        return items

    def _rss_feed_configs(self) -> list[dict[str, Any]]:
        """Return a list of RSS feed configs from the sources config.

        Each entry has keys: url, fallback_url (optional), source_name.
        Supports the original ``blog`` key and any additional top-level
        entries with ``type: rss``.
        """
        feeds: list[dict[str, Any]] = []

        # Original blog key
        blog_cfg = self.config.get("blog", {})
        if blog_cfg.get("url"):
            feeds.append({
                "url": blog_cfg["url"],
                "fallback_url": blog_cfg.get("fallback_url", ""),
                "source_name": "aptoslabs.com/blog",
            })

        # Additional RSS feeds (e.g. medium)
        for key, cfg in self.config.items():
            if key in ("blog", "aips", "forum", "youtube", "governance"):
                continue
            if isinstance(cfg, dict) and cfg.get("type") == "rss" and cfg.get("url"):
                feeds.append({
                    "url": cfg["url"],
                    "fallback_url": cfg.get("fallback_url", ""),
                    "source_name": key,
                })

        return feeds

    def _scrape_all_blogs(self, since: date, until: date) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for feed_cfg in self._rss_feed_configs():
            items.extend(self._scrape_blog(feed_cfg, since, until))
        return items

    def _scrape_blog(self, feed_cfg: dict[str, Any], since: date, until: date) -> list[dict[str, Any]]:
        url = feed_cfg["url"]
        source_name = feed_cfg.get("source_name", "blog")

        logger.info("Scraping blog RSS from %s", url)
        items: list[dict[str, Any]] = []

        try:
            with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.warning("RSS feed failed for %s, trying fallback URL", url)
            fallback = feed_cfg.get("fallback_url", "")
            if fallback:
                return self._scrape_blog_html(fallback, since, until)
            return []

        feed = feedparser.parse(resp.text)
        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = date(*entry.published_parsed[:3])
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published = date(*entry.updated_parsed[:3])

            if published is None:
                continue
            if published < since or published > until:
                continue

            title = entry.get("title", "Untitled")
            link = entry.get("link", "")
            summary = entry.get("summary", "")
            if summary:
                summary = BeautifulSoup(summary, "html.parser").get_text()[:500]

            items.append(
                {
                    "id": f"blog:{link}",
                    "source_type": "blog",
                    "title": title,
                    "body": summary,
                    "url": link,
                    "date": published.isoformat(),
                    "repo": source_name,
                }
            )

        return items

    def _scrape_blog_html(
        self, url: str, since: date, until: date
    ) -> list[dict[str, Any]]:
        """Fallback: scrape blog listing page via HTML."""
        logger.info("Scraping blog HTML from %s", url)
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
        except Exception:
            logger.exception("Blog HTML scrape failed")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items: list[dict[str, Any]] = []

        for article in soup.find_all("article"):
            title_el = article.find(["h2", "h3"])
            link_el = article.find("a", href=True)
            if not title_el or not link_el:
                continue
            title = title_el.get_text(strip=True)
            link = link_el["href"]
            if not link.startswith("http"):
                link = url.rstrip("/") + "/" + link.lstrip("/")

            items.append(
                {
                    "id": f"blog:{link}",
                    "source_type": "blog",
                    "title": title,
                    "url": link,
                    "date": date.today().isoformat(),
                    "repo": "aptoslabs.com/blog",
                }
            )

        return items

    def _scrape_forum(self, since: date, until: date) -> list[dict[str, Any]]:
        forum_cfg = self.config.get("forum", {})
        base_url = forum_cfg.get("base_url", "")
        if not base_url:
            return []

        min_likes = forum_cfg.get("min_likes", 0)
        min_replies = forum_cfg.get("min_replies", 0)
        categories = forum_cfg.get("categories", [])
        items: list[dict[str, Any]] = []

        for cat in categories:
            cat_slug = cat.get("slug", "")
            cat_id = cat.get("id", "")
            api_url = f"{base_url}/c/{cat_slug}/{cat_id}.json"
            logger.info("Scraping forum category: %s", cat_slug)

            try:
                with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
                    resp = client.get(api_url)
                    resp.raise_for_status()
                    data = resp.json()
            except Exception:
                logger.exception("Forum API failed for category %s", cat_slug)
                continue

            topics = data.get("topic_list", {}).get("topics", [])
            for topic in topics:
                created = topic.get("created_at", "")
                if not created:
                    continue
                try:
                    topic_date = datetime.fromisoformat(
                        created.replace("Z", "+00:00")
                    ).date()
                except ValueError:
                    continue

                if topic_date < since or topic_date > until:
                    continue
                if topic.get("like_count", 0) < min_likes:
                    continue
                if topic.get("posts_count", 1) - 1 < min_replies:
                    continue

                topic_id = topic["id"]
                slug = topic.get("slug", "")
                items.append(
                    {
                        "id": f"forum:{topic_id}",
                        "source_type": "forum",
                        "title": topic.get("title", ""),
                        "url": f"{base_url}/t/{slug}/{topic_id}",
                        "date": topic_date.isoformat(),
                        "repo": "forum.aptosfoundation.org",
                        "category": cat_slug,
                        "likes": topic.get("like_count", 0),
                        "replies": topic.get("posts_count", 1) - 1,
                    }
                )

        return items
