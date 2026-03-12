"""Scraper for on-chain governance proposals from the Aptos mainnet."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from src.scrapers.base import BaseScraper
from src.utils.config_loader import load_sources_config

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 30.0
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
STATE_FILE = DATA_DIR / "state.json"


def _load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_scrape": None, "etags": {}, "known_aips": {}, "known_proposals": {}}


def _save_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


class GovernanceScraper(BaseScraper):
    name = "governance"

    def __init__(self, http_client: httpx.Client | None = None):
        self.config = load_sources_config().get("governance", {})
        self._http_client = http_client

    def scrape(self, since: date, until: date) -> list[dict[str, Any]]:
        api_url = self.config.get("api_url", "")
        if not api_url:
            logger.warning("No governance API URL configured, skipping")
            return []

        voting_address = self.config.get("voting_address", "0x1")
        lookback_days = self.config.get("lookback_days", 45)

        state = _load_state()
        known_proposals = state.get("known_proposals", {})

        items: list[dict[str, Any]] = []

        try:
            next_proposal_id = self._get_next_proposal_id(api_url, voting_address)
            if next_proposal_id is None:
                return []

            table_handle = self._get_voting_table_handle(api_url, voting_address)
            if not table_handle:
                return []

            for proposal_id in range(max(0, next_proposal_id - 50), next_proposal_id):
                try:
                    proposal = self._get_proposal(api_url, table_handle, proposal_id)
                    if proposal is None:
                        continue

                    proposal_state = self._determine_state(proposal)
                    creation_ts = int(proposal.get("creation_time_secs", 0))
                    proposal_date = datetime.fromtimestamp(
                        creation_ts, tz=timezone.utc
                    ).date()

                    # Check if this is within our lookback window
                    days_ago = (until - proposal_date).days
                    if days_ago > lookback_days:
                        continue

                    str_id = str(proposal_id)
                    prev_state = known_proposals.get(str_id, {}).get("state")

                    # Emit item for new proposals or state transitions
                    if prev_state is None or prev_state != proposal_state:
                        metadata_url = proposal.get("metadata", {}).get(
                            "metadata_url", ""
                        )
                        title = self._extract_title(proposal, proposal_id)
                        description = proposal.get("metadata", {}).get(
                            "description", ""
                        )[:500]

                        if proposal_date < since or proposal_date > until:
                            # Still update known state even for out-of-range proposals
                            known_proposals[str_id] = {
                                "state": proposal_state,
                                "title": title,
                            }
                            continue

                        items.append(
                            {
                                "id": f"governance:{proposal_id}:{proposal_state}",
                                "source_type": "governance_proposal",
                                "title": f"Governance Proposal #{proposal_id}: {title}",
                                "body": description,
                                "url": f"https://governance.aptosfoundation.org/proposal/{proposal_id}",
                                "date": proposal_date.isoformat(),
                                "repo": "aptos-governance",
                                "proposal_id": proposal_id,
                                "state": proposal_state,
                            }
                        )

                    known_proposals[str_id] = {
                        "state": proposal_state,
                        "title": self._extract_title(proposal, proposal_id),
                    }

                except Exception:
                    logger.exception(
                        "Failed to fetch proposal %d", proposal_id
                    )
                    continue

        except Exception:
            logger.exception("Governance scraper failed")

        state["known_proposals"] = known_proposals
        _save_state(state)

        return items

    def _get_client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        return httpx.Client(timeout=HTTP_TIMEOUT)

    def _get_next_proposal_id(
        self, api_url: str, voting_address: str
    ) -> int | None:
        """Read GovernanceConfig to get next_proposal_id."""
        client = self._get_client()
        try:
            resp = client.get(
                f"{api_url}/accounts/{voting_address}/resource/"
                "0x1::aptos_governance::GovernanceConfig"
            )
            resp.raise_for_status()
            data = resp.json()
            return int(data.get("data", {}).get("next_proposal_id", 0))
        except Exception:
            logger.exception("Failed to get GovernanceConfig")
            return None
        finally:
            if self._http_client is None:
                client.close()

    def _get_voting_table_handle(
        self, api_url: str, voting_address: str
    ) -> str:
        """Read VotingForum to get the proposals table handle."""
        client = self._get_client()
        try:
            resp = client.get(
                f"{api_url}/accounts/{voting_address}/resource/"
                "0x1::voting::VotingForum%3C0x1::governance_proposal::GovernanceProposal%3E"
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("proposals", {}).get("handle", "")
        except Exception:
            logger.exception("Failed to get VotingForum table handle")
            return ""
        finally:
            if self._http_client is None:
                client.close()

    def _get_proposal(
        self, api_url: str, table_handle: str, proposal_id: int
    ) -> dict[str, Any] | None:
        """Fetch a single proposal from the table."""
        client = self._get_client()
        try:
            resp = client.post(
                f"{api_url}/tables/{table_handle}/item",
                json={
                    "key_type": "u64",
                    "value_type": "0x1::voting::Proposal<0x1::governance_proposal::GovernanceProposal>",
                    "key": str(proposal_id),
                },
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            logger.warning("HTTP error fetching proposal %d: %s", proposal_id, exc)
            return None
        except Exception:
            logger.warning("Failed to fetch proposal %d", proposal_id)
            return None
        finally:
            if self._http_client is None:
                client.close()

    def _determine_state(self, proposal: dict[str, Any]) -> str:
        """Determine the current state of a proposal."""
        is_resolved = proposal.get("is_resolved", False)
        if isinstance(is_resolved, str):
            is_resolved = is_resolved.lower() == "true"

        if is_resolved:
            # Check if it passed based on yes/no votes
            yes_votes = int(proposal.get("yes_votes", 0))
            no_votes = int(proposal.get("no_votes", 0))
            if yes_votes > no_votes:
                return "passed"
            return "rejected"

        # Check if voting period has ended
        expiration = int(proposal.get("expiration_secs", 0))
        now = datetime.now(tz=timezone.utc).timestamp()
        if now > expiration:
            return "expired"

        return "voting"

    def _extract_title(self, proposal: dict[str, Any], proposal_id: int) -> str:
        """Extract title from proposal metadata."""
        metadata = proposal.get("metadata", {})
        if isinstance(metadata, dict):
            # The metadata might have a "title" key in its data map
            data = metadata.get("data", [])
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and entry.get("key") == "title":
                        return entry.get("value", f"Proposal {proposal_id}")
            # Or it might be a direct field
            title = metadata.get("title", "")
            if title:
                return title
        return f"Proposal {proposal_id}"
