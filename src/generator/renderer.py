"""Jinja2 rendering for Markdown and HTML newsletter output."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from premailer import transform

from src.utils.config_loader import load_newsletter_config

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "newsletters"


def _build_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _build_context(
    summaries: dict[str, Any],
    categorized: dict[str, list[dict[str, Any]]],
    month_year: str,
) -> dict[str, Any]:
    """Build the template context from summaries and categorized items."""
    config = load_newsletter_config()
    branding = config.get("branding", {})
    sections_config = config["sections"]

    sections = []
    for sec_cfg in sections_config:
        sid = sec_cfg["id"]
        summary_text = summaries.get("sections", {}).get(sid, "")
        items = categorized.get(sid, [])
        if summary_text or items:
            sections.append(
                {
                    "id": sid,
                    "title": sec_cfg["title"],
                    "summary": summary_text,
                    "entries": items,
                }
            )

    return {
        "month_year": month_year,
        "intro": summaries.get("intro", ""),
        "sections": sections,
        "branding": branding,
    }


def render_markdown(
    summaries: dict[str, Any],
    categorized: dict[str, list[dict[str, Any]]],
    month_year: str,
) -> str:
    """Render the Markdown newsletter."""
    env = _build_jinja_env()
    template = env.get_template("newsletter.md.j2")
    context = _build_context(summaries, categorized, month_year)
    return template.render(**context)


def render_html(
    summaries: dict[str, Any],
    categorized: dict[str, list[dict[str, Any]]],
    month_year: str,
) -> str:
    """Render the HTML newsletter with inlined CSS."""
    env = _build_jinja_env()
    template = env.get_template("newsletter.html.j2")
    context = _build_context(summaries, categorized, month_year)
    raw_html = template.render(**context)
    return transform(raw_html)


def save_output(month_year: str, markdown: str, html: str) -> tuple[Path, Path]:
    """Save rendered newsletter files to the output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = OUTPUT_DIR / f"{month_year}.md"
    html_path = OUTPUT_DIR / f"{month_year}.html"

    md_path.write_text(markdown)
    html_path.write_text(html)

    logger.info("Saved newsletter: %s, %s", md_path, html_path)
    return md_path, html_path
