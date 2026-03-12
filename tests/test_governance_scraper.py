"""Tests for the on-chain governance scraper."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.scrapers.governance import GovernanceScraper, _load_state, _save_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Timestamp for Feb 15, 2026
FEB_15_TS = int(datetime(2026, 2, 15, 12, 0, tzinfo=timezone.utc).timestamp())
# Timestamp for Jan 5, 2026
JAN_5_TS = int(datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc).timestamp())
# Future expiration
FUTURE_EXPIRATION = int(datetime(2027, 1, 1, tzinfo=timezone.utc).timestamp())
# Past expiration
PAST_EXPIRATION = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())


def _make_proposal(
    *,
    creation_ts: int = FEB_15_TS,
    yes_votes: int = 100,
    no_votes: int = 10,
    is_resolved: bool = True,
    expiration_secs: int = FUTURE_EXPIRATION,
    title: str = "Test Proposal",
    description: str = "A test governance proposal.",
) -> dict:
    return {
        "creation_time_secs": str(creation_ts),
        "yes_votes": str(yes_votes),
        "no_votes": str(no_votes),
        "is_resolved": str(is_resolved).lower(),
        "expiration_secs": str(expiration_secs),
        "metadata": {
            "data": [
                {"key": "title", "value": title},
            ],
            "description": description,
        },
    }


def _mock_client(
    next_proposal_id: int = 5,
    table_handle: str = "0xhandle123",
    proposals: dict[int, dict] | None = None,
):
    """Create a mock httpx.Client for governance API calls."""
    mock = MagicMock()

    def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "GovernanceConfig" in url:
            resp.json.return_value = {
                "data": {"next_proposal_id": str(next_proposal_id)}
            }
        elif "VotingForum" in url:
            resp.json.return_value = {
                "data": {"proposals": {"handle": table_handle}}
            }
        else:
            resp.json.return_value = {}
        return resp

    def fake_post(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        body = kwargs.get("json", {})
        key = int(body.get("key", 0))
        if proposals and key in proposals:
            resp.json.return_value = proposals[key]
        else:
            resp.json.return_value = _make_proposal()
        return resp

    mock.get = fake_get
    mock.post = fake_post
    return mock


# ---------------------------------------------------------------------------
# GovernanceScraper
# ---------------------------------------------------------------------------


class TestGovernanceScraper:
    """Test GovernanceScraper with mocked API responses."""

    @patch("src.scrapers.governance._save_state")
    @patch("src.scrapers.governance._load_state")
    @patch("src.scrapers.governance.load_sources_config")
    def test_scrape_new_proposal(
        self, mock_config, mock_load_state, mock_save_state
    ):
        """A new proposal within the date range is returned."""
        mock_config.return_value = {
            "governance": {
                "api_url": "https://api.mainnet.aptoslabs.com/v1",
                "voting_address": "0x1",
                "lookback_days": 45,
            }
        }
        mock_load_state.return_value = {"known_proposals": {}}

        proposals = {
            4: _make_proposal(title="Enable Feature X"),
        }
        http_client = _mock_client(next_proposal_id=5, proposals=proposals)

        scraper = GovernanceScraper(http_client=http_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        # Proposals 0-4 are checked, but only those in range with state changes appear
        found = [i for i in items if "Enable Feature X" in i["title"]]
        assert len(found) == 1
        item = found[0]
        assert item["source_type"] == "governance_proposal"
        assert item["state"] == "passed"
        assert item["proposal_id"] == 4
        assert "governance.aptosfoundation.org/proposal/4" in item["url"]
        assert item["date"] == "2026-02-15"

    @patch("src.scrapers.governance._save_state")
    @patch("src.scrapers.governance._load_state")
    @patch("src.scrapers.governance.load_sources_config")
    def test_scrape_known_proposal_no_state_change(
        self, mock_config, mock_load_state, mock_save_state
    ):
        """A known proposal with the same state is not re-emitted."""
        mock_config.return_value = {
            "governance": {
                "api_url": "https://api.mainnet.aptoslabs.com/v1",
                "voting_address": "0x1",
                "lookback_days": 45,
            }
        }
        mock_load_state.return_value = {
            "known_proposals": {
                "4": {"state": "passed", "title": "Enable Feature X"},
            }
        }

        proposals = {
            4: _make_proposal(title="Enable Feature X"),
        }
        http_client = _mock_client(next_proposal_id=5, proposals=proposals)

        scraper = GovernanceScraper(http_client=http_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        # No state change for proposal 4, so it should not be emitted
        found = [i for i in items if i.get("proposal_id") == 4]
        assert len(found) == 0

    @patch("src.scrapers.governance._save_state")
    @patch("src.scrapers.governance._load_state")
    @patch("src.scrapers.governance.load_sources_config")
    def test_scrape_state_transition_emits_item(
        self, mock_config, mock_load_state, mock_save_state
    ):
        """A proposal that changed state is emitted."""
        mock_config.return_value = {
            "governance": {
                "api_url": "https://api.mainnet.aptoslabs.com/v1",
                "voting_address": "0x1",
                "lookback_days": 45,
            }
        }
        mock_load_state.return_value = {
            "known_proposals": {
                "4": {"state": "voting", "title": "Enable Feature X"},
            }
        }

        proposals = {
            4: _make_proposal(title="Enable Feature X", is_resolved=True),
        }
        http_client = _mock_client(next_proposal_id=5, proposals=proposals)

        scraper = GovernanceScraper(http_client=http_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        found = [i for i in items if i.get("proposal_id") == 4]
        assert len(found) == 1
        assert found[0]["state"] == "passed"

    @patch("src.scrapers.governance._save_state")
    @patch("src.scrapers.governance._load_state")
    @patch("src.scrapers.governance.load_sources_config")
    def test_scrape_rejected_proposal(
        self, mock_config, mock_load_state, mock_save_state
    ):
        """A proposal that was rejected (more no votes) is labeled rejected."""
        mock_config.return_value = {
            "governance": {
                "api_url": "https://api.mainnet.aptoslabs.com/v1",
                "voting_address": "0x1",
                "lookback_days": 45,
            }
        }
        mock_load_state.return_value = {"known_proposals": {}}

        proposals = {
            4: _make_proposal(
                title="Bad Proposal",
                yes_votes=10,
                no_votes=100,
                is_resolved=True,
            ),
        }
        http_client = _mock_client(next_proposal_id=5, proposals=proposals)

        scraper = GovernanceScraper(http_client=http_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        found = [i for i in items if i.get("proposal_id") == 4]
        assert len(found) == 1
        assert found[0]["state"] == "rejected"

    @patch("src.scrapers.governance._save_state")
    @patch("src.scrapers.governance._load_state")
    @patch("src.scrapers.governance.load_sources_config")
    def test_scrape_voting_proposal(
        self, mock_config, mock_load_state, mock_save_state
    ):
        """A proposal still in voting period is labeled voting."""
        mock_config.return_value = {
            "governance": {
                "api_url": "https://api.mainnet.aptoslabs.com/v1",
                "voting_address": "0x1",
                "lookback_days": 45,
            }
        }
        mock_load_state.return_value = {"known_proposals": {}}

        proposals = {
            4: _make_proposal(
                title="Active Proposal",
                is_resolved=False,
                expiration_secs=FUTURE_EXPIRATION,
            ),
        }
        http_client = _mock_client(next_proposal_id=5, proposals=proposals)

        scraper = GovernanceScraper(http_client=http_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        found = [i for i in items if i.get("proposal_id") == 4]
        assert len(found) == 1
        assert found[0]["state"] == "voting"

    @patch("src.scrapers.governance._save_state")
    @patch("src.scrapers.governance._load_state")
    @patch("src.scrapers.governance.load_sources_config")
    def test_scrape_no_api_url_returns_empty(
        self, mock_config, mock_load_state, mock_save_state
    ):
        mock_config.return_value = {"governance": {}}
        mock_load_state.return_value = {"known_proposals": {}}

        scraper = GovernanceScraper()
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))
        assert items == []

    @patch("src.scrapers.governance._save_state")
    @patch("src.scrapers.governance._load_state")
    @patch("src.scrapers.governance.load_sources_config")
    def test_scrape_api_error_handled_gracefully(
        self, mock_config, mock_load_state, mock_save_state
    ):
        mock_config.return_value = {
            "governance": {
                "api_url": "https://api.mainnet.aptoslabs.com/v1",
                "voting_address": "0x1",
                "lookback_days": 45,
            }
        }
        mock_load_state.return_value = {"known_proposals": {}}

        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Network error")

        scraper = GovernanceScraper(http_client=mock_client)
        items = scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))
        assert items == []

    @patch("src.scrapers.governance._save_state")
    @patch("src.scrapers.governance._load_state")
    @patch("src.scrapers.governance.load_sources_config")
    def test_scrape_saves_state(
        self, mock_config, mock_load_state, mock_save_state
    ):
        """Verify that scraper saves updated known_proposals state."""
        mock_config.return_value = {
            "governance": {
                "api_url": "https://api.mainnet.aptoslabs.com/v1",
                "voting_address": "0x1",
                "lookback_days": 45,
            }
        }
        mock_load_state.return_value = {"known_proposals": {}}

        proposals = {
            4: _make_proposal(title="Save State Test"),
        }
        http_client = _mock_client(next_proposal_id=5, proposals=proposals)

        scraper = GovernanceScraper(http_client=http_client)
        scraper.scrape(since=date(2026, 2, 1), until=date(2026, 2, 28))

        mock_save_state.assert_called_once()
        saved_state = mock_save_state.call_args[0][0]
        assert "4" in saved_state["known_proposals"]
        assert saved_state["known_proposals"]["4"]["state"] == "passed"
