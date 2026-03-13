"""AI-powered item classification for the newsletter pipeline.

Sits between ``filter_items()`` and ``categorize()`` in the generation
pipeline.  Uses the Anthropic **batch** API to classify every item into
one of four categories (``breaking``, ``dev-facing``, ``node-operator``,
``internal``) and tag each with its target audience.  Only ``breaking``
and ``dev-facing`` items are returned — the rest are dropped so the
newsletter stays focused on developer-relevant changes.

Set the environment variable ``SKIP_CLASSIFY=true`` to bypass
classification entirely (useful for fast dry runs).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import anthropic

from src.utils.config_loader import load_newsletter_config

logger = logging.getLogger(__name__)

CLASSIFICATION_MODEL = "claude-sonnet-4-6"
POLL_INTERVAL_SECONDS = 10
KEEP_CATEGORIES = {"breaking", "dev-facing"}
VALID_CATEGORIES = {"breaking", "dev-facing", "node-operator", "internal"}
VALID_AUDIENCES = {
    "dapp-developers",
    "sdk-users",
    "move-developers",
    "wallet-builders",
    "indexer-users",
    "node-operators",
}

CLASSIFICATION_PROMPT = """\
You are a changelog classifier for the Aptos developer newsletter.
Classify the following item into exactly one category:

"breaking" — requires developers to change their code, update dependencies, config, or migration steps
"dev-facing" — a fix, feature, or improvement that a dApp developer, SDK user, or tooling user would notice or care about
"node-operator" — only relevant to validators, fullnode operators, or infrastructure teams running nodes
"internal" — refactors, CI changes, test cleanup, build system changes, dead code removal, or dependency bumps with no behavior change

Item:
Title: {title}
Repo: {repo}
Type: {source_type}
Description: {body}

Classification rules:

Titles with "refactor", "cleanup", "rename", "remove dead", "chore", "bump version", "migrate CI", "test" → lean internal unless description reveals external impact
PRs touching storage, consensus, networking internals with no SDK/API/framework surface change → node-operator
Bug fixes that change developer-observable behavior → dev-facing even if small
Security fixes → always breaking or dev-facing, never internal
If developer must change any code or config → breaking

Respond with JSON only. No markdown, no explanation.
{{"category": "...", "audience": [...], "one_liner": "..."}}
Valid audience values (pick 1–3): dapp-developers, sdk-users, move-developers, wallet-builders, indexer-users, node-operators
The "one_liner" should be a clean, plain-English summary under 15 words suitable for a changelog entry."""


def _build_prompt(item: dict[str, Any]) -> str:
    """Build a classification prompt for a single item."""
    return CLASSIFICATION_PROMPT.format(
        title=item.get("title", ""),
        repo=item.get("repo", ""),
        source_type=item.get("source_type", ""),
        body=(item.get("body", "") or "")[:500],
    )


def _parse_classification(raw_text: str) -> dict[str, Any] | None:
    """Parse the JSON response from a classification call.

    Returns a dict with ``category``, ``audience``, and ``one_liner``
    keys, or *None* if parsing fails or the values are invalid.
    """
    try:
        data = json.loads(raw_text.strip())
    except (json.JSONDecodeError, TypeError):
        return None

    category = data.get("category", "")
    if category not in VALID_CATEGORIES:
        return None

    audience = data.get("audience", [])
    if not isinstance(audience, list):
        audience = [audience]
    audience = [a for a in audience if a in VALID_AUDIENCES]

    one_liner = data.get("one_liner", "")
    if not isinstance(one_liner, str):
        one_liner = ""

    return {
        "category": category,
        "audience": audience,
        "one_liner": one_liner,
    }


def _create_client() -> anthropic.Anthropic:
    """Create an Anthropic client using the environment API key."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")
    return anthropic.Anthropic(api_key=api_key)


def _classify_via_batch(
    client: anthropic.Anthropic,
    items: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Submit items to the batch API and return a mapping of custom_id → parsed result.

    Each item's ``id`` field is used as the ``custom_id`` in the batch
    request so results can be matched back.
    """
    requests = []
    for item in items:
        custom_id = str(item.get("id", ""))
        if not custom_id:
            continue
        requests.append({
            "custom_id": custom_id,
            "params": {
                "model": CLASSIFICATION_MODEL,
                "max_tokens": 256,
                "messages": [{"role": "user", "content": _build_prompt(item)}],
            },
        })

    if not requests:
        return {}

    logger.info("Submitting batch of %d classification requests", len(requests))
    batch = client.messages.batches.create(requests=requests)
    batch_id = batch.id
    logger.info("Batch created: %s", batch_id)

    # Poll until complete
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        status = batch.processing_status
        logger.debug("Batch %s status: %s", batch_id, status)
        if status == "ended":
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    # Collect results
    results: dict[str, dict[str, Any]] = {}
    for result in client.messages.batches.results(batch_id):
        custom_id = result.custom_id
        if result.result.type == "succeeded":
            message = result.result.message
            if message.content and message.content[0].type == "text":
                parsed = _parse_classification(message.content[0].text)
                if parsed is not None:
                    results[custom_id] = parsed
                else:
                    logger.warning(
                        "Failed to parse classification for item %s",
                        custom_id,
                    )
            else:
                logger.warning("No text content for item %s", custom_id)
        else:
            logger.warning(
                "Batch result for item %s was not successful: %s",
                custom_id,
                result.result.type,
            )

    return results


def classify_items(
    items: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Classify items using Claude batch API.

    Adds ``category``, ``audience``, and ``one_liner`` fields to each
    item.  Returns only ``breaking`` and ``dev-facing`` items.

    Parameters
    ----------
    items:
        Items returned by :func:`src.processor.filter.filter_items`.
    config:
        Newsletter config dict (unused currently, reserved for future
        options).  If *None*, loaded automatically.

    Returns
    -------
    list[dict]
        Items classified as ``breaking`` or ``dev-facing``, with the
        new classification fields attached.
    """
    if not items:
        return []

    # Allow skipping classification entirely
    if os.environ.get("SKIP_CLASSIFY", "").lower() in ("true", "1", "yes"):
        logger.info("SKIP_CLASSIFY is set — passing %d items through unclassified", len(items))
        return list(items)

    try:
        client = _create_client()
        results = _classify_via_batch(client, items)
    except Exception:
        logger.exception(
            "Batch classification failed — returning all %d items unclassified",
            len(items),
        )
        return list(items)

    # Apply classifications
    counts: dict[str, int] = {"breaking": 0, "dev-facing": 0, "node-operator": 0, "internal": 0}
    classified: list[dict[str, Any]] = []

    for item in items:
        item_id = str(item.get("id", ""))
        classification = results.get(item_id)

        if classification is None:
            # Default unclassified items to internal (fail-safe: drop rather than include noise)
            counts["internal"] += 1
            continue

        category = classification["category"]
        counts[category] = counts.get(category, 0) + 1

        if category not in KEEP_CATEGORIES:
            continue

        # Attach classification fields to a copy of the item
        enriched = {**item, **classification}
        classified.append(enriched)

    logger.info(
        "Classification results: %s — keeping %d items",
        ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
        len(classified),
    )
    return classified
