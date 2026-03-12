"""Claude API integration for newsletter summarization."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import anthropic

from src.utils.config_loader import load_newsletter_config

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS_SECTION = 2048
DEFAULT_MAX_TOKENS_INTRO = 512
DEFAULT_TEMPERATURE = 0.3
MAX_RETRIES = 3


def _get_summarization_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return summarization settings from config with sensible defaults."""
    if config is None:
        config = load_newsletter_config()
    summarization = config.get("summarization", {})
    return {
        "model": summarization.get("model", DEFAULT_MODEL),
        "max_tokens_section": summarization.get("max_tokens_section", DEFAULT_MAX_TOKENS_SECTION),
        "max_tokens_intro": summarization.get("max_tokens_intro", DEFAULT_MAX_TOKENS_INTRO),
        "temperature": summarization.get("temperature", DEFAULT_TEMPERATURE),
        "style": summarization.get("style", ""),
    }


def create_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")
    return anthropic.Anthropic(api_key=api_key)


def _call_with_retry(
    client: anthropic.Anthropic,
    model: str,
    max_tokens: int,
    messages: list[dict[str, str]],
    temperature: float = DEFAULT_TEMPERATURE,
) -> str:
    """Call the Claude API with exponential backoff on transient failures."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages,
            )
            return message.content[0].text
        except anthropic.RateLimitError:
            if attempt == MAX_RETRIES:
                raise
            wait = 2 ** attempt
            logger.warning(
                "Rate limited (attempt %d/%d), retrying in %ds",
                attempt, MAX_RETRIES, wait,
            )
            time.sleep(wait)
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500 and attempt < MAX_RETRIES:
                wait = 2 ** attempt
                logger.warning(
                    "API error %d (attempt %d/%d), retrying in %ds",
                    exc.status_code, attempt, MAX_RETRIES, wait,
                )
                time.sleep(wait)
            else:
                raise
    # Should not reach here, but satisfy type checker
    raise RuntimeError("Exhausted retries")  # pragma: no cover


def summarize_section(
    client: anthropic.Anthropic,
    section_id: str,
    items: list[dict[str, Any]],
    prompt: str,
    sum_config: dict[str, Any] | None = None,
) -> str:
    """Generate a prose summary for a newsletter section."""
    if not items:
        return ""

    if sum_config is None:
        sum_config = _get_summarization_config()

    items_text = _format_items_for_prompt(items)

    # Prepend style instruction when configured
    style = sum_config.get("style", "")
    style_prefix = f"Write in a {style} style.\n\n" if style else ""

    full_prompt = f"{style_prefix}{prompt}\n\nItems:\n{items_text}"

    logger.info("Summarizing section '%s' (%d items)", section_id, len(items))

    return _call_with_retry(
        client,
        model=sum_config["model"],
        max_tokens=sum_config["max_tokens_section"],
        messages=[{"role": "user", "content": full_prompt}],
        temperature=sum_config.get("temperature", DEFAULT_TEMPERATURE),
    )


def summarize_intro(
    client: anthropic.Anthropic,
    section_summaries: dict[str, str],
    month_year: str,
    sum_config: dict[str, Any] | None = None,
) -> str:
    """Generate the newsletter introduction."""
    config = load_newsletter_config()
    intro_prompt = config.get("intro_prompt", "").format(month_year=month_year)

    if sum_config is None:
        sum_config = _get_summarization_config(config)

    summaries_text = "\n\n".join(
        f"## {sid}\n{text}" for sid, text in section_summaries.items() if text
    )

    style = sum_config.get("style", "")
    style_prefix = f"Write in a {style} style.\n\n" if style else ""

    full_prompt = f"{style_prefix}{intro_prompt}\n\nSection summaries:\n{summaries_text}"

    logger.info("Generating newsletter intro for %s", month_year)

    return _call_with_retry(
        client,
        model=sum_config["model"],
        max_tokens=sum_config["max_tokens_intro"],
        messages=[{"role": "user", "content": full_prompt}],
        temperature=sum_config.get("temperature", DEFAULT_TEMPERATURE),
    )


def generate_all_summaries(
    categorized: dict[str, list[dict[str, Any]]],
    month_year: str,
    skip: bool = False,
) -> dict[str, Any]:
    """Generate summaries for all sections and the intro.

    If skip=True, returns raw item titles instead of Claude summaries.
    """
    config = load_newsletter_config()
    sections_config = {s["id"]: s for s in config["sections"]}
    sum_config = _get_summarization_config(config)

    section_summaries: dict[str, str] = {}

    if skip:
        for section_id, items in categorized.items():
            if items:
                lines = [f"- {item['title']}" for item in items]
                section_summaries[section_id] = "\n".join(lines)
            else:
                section_summaries[section_id] = ""
        intro = f"Developer newsletter for {month_year}."
    else:
        client = create_client()
        for section_id, items in categorized.items():
            prompt = sections_config.get(section_id, {}).get("prompt", "Summarize these items.")
            try:
                section_summaries[section_id] = summarize_section(
                    client, section_id, items, prompt, sum_config=sum_config,
                )
            except Exception:
                logger.exception(
                    "Failed to summarize section '%s'; falling back to bullet list",
                    section_id,
                )
                if items:
                    lines = [f"- {item['title']}" for item in items]
                    section_summaries[section_id] = "\n".join(lines)
                else:
                    section_summaries[section_id] = ""

        try:
            intro = summarize_intro(client, section_summaries, month_year, sum_config=sum_config)
        except Exception:
            logger.exception(
                "Failed to generate intro; using fallback",
            )
            intro = f"Developer newsletter for {month_year}."

    return {
        "intro": intro,
        "sections": section_summaries,
    }


def _format_items_for_prompt(items: list[dict[str, Any]]) -> str:
    """Format items into a text block for the Claude prompt."""
    lines = []
    for item in items:
        parts = [f"- [{item.get('source_type', 'item')}] {item['title']}"]
        if item.get("repo"):
            parts.append(f"  Repo: {item['repo']}")
        if item.get("url"):
            parts.append(f"  URL: {item['url']}")
        if item.get("date"):
            parts.append(f"  Date: {item['date']}")
        if item.get("body"):
            body_preview = item["body"][:300].replace("\n", " ")
            parts.append(f"  Description: {body_preview}")
        if item.get("labels"):
            parts.append(f"  Labels: {', '.join(item['labels'])}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)
