"""Changelog generation: group items by repo and render comprehensive Markdown + HTML."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from src.utils.config_loader import load_newsletter_config

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "output" / "changelogs"
DOCS_DIR = PROJECT_ROOT / "docs" / "changelogs"


def _build_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def group_by_repo(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group items by repo name, sorted alphabetically by repo."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        repo = item.get("repo", "unknown")
        groups[repo].append(item)

    # Sort items within each repo by date descending
    for repo_items in groups.values():
        repo_items.sort(key=lambda x: x.get("date", ""), reverse=True)

    return dict(sorted(groups.items()))


def _build_stats(items: list[dict[str, Any]]) -> dict[str, int]:
    """Compute summary stats for the changelog."""
    repos = set()
    releases = 0
    prs = 0
    commits = 0
    changelog_entries = 0

    for item in items:
        repos.add(item.get("repo", ""))
        st = item.get("source_type", "")
        if st == "release":
            releases += 1
        elif st == "pr":
            prs += 1
        elif st == "commit":
            commits += 1
        elif st == "changelog_entry":
            changelog_entries += 1

    return {
        "total": len(items),
        "repos_active": len(repos),
        "releases": releases,
        "prs": prs,
        "commits": commits,
        "changelog_entries": changelog_entries,
    }


def render_changelog_markdown(
    items: list[dict[str, Any]], month_year: str
) -> str:
    """Render the full changelog as Markdown."""
    env = _build_jinja_env()
    template = env.get_template("changelog.md.j2")
    grouped = group_by_repo(items)
    stats = _build_stats(items)

    return template.render(
        month_year=month_year,
        grouped=grouped,
        stats=stats,
    )


def render_changelog_html(
    items: list[dict[str, Any]], month_year: str
) -> str:
    """Render the full changelog as a standalone HTML page."""
    env = _build_jinja_env()
    template = env.get_template("changelog.html.j2")
    config = load_newsletter_config()
    branding = config.get("branding", {})
    grouped = group_by_repo(items)
    stats = _build_stats(items)

    return template.render(
        month_year=month_year,
        grouped=grouped,
        stats=stats,
        branding=branding,
    )


def render_changelog_index(months: list[str]) -> str:
    """Regenerate the docs/index.html listing all available changelogs."""
    config = load_newsletter_config()
    branding = config.get("branding", {})
    changelog_base_url = branding.get("changelog_base_url", "changelogs")

    months_sorted = sorted(months, reverse=True)

    lines = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'  <title>{branding.get("title", "Aptos")} — Changelog Archive</title>',
        "  <style>",
        "    body {",
        f'      background-color: {branding.get("color_bg", "#0B1221")};',
        f'      color: {branding.get("color_text", "#E8E8E8")};',
        "      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;",
        "      max-width: 600px;",
        "      margin: 40px auto;",
        "      padding: 0 24px;",
        "    }",
        f'    h1 {{ color: {branding.get("color_primary", "#00D4AA")}; }}',
        f'    a {{ color: {branding.get("color_primary", "#00D4AA")}; text-decoration: none; }}',
        "    a:hover { text-decoration: underline; }",
        "    ul { list-style: none; padding: 0; }",
        "    li { margin: 12px 0; font-size: 18px; }",
        f'    .footer {{ margin-top: 40px; font-size: 13px; color: {branding.get("color_muted", "#8B95A5")}; }}',
        "  </style>",
        "</head>",
        "<body>",
        f'  <h1>{branding.get("title", "Aptos Developer Monthly")} — Changelog Archive</h1>',
        "  <ul>",
    ]

    for m in months_sorted:
        lines.append(f'    <li><a href="changelogs/{m}.html">{m}</a></li>')

    lines.extend([
        "  </ul>",
        f'  <div class="footer">{branding.get("footer", "")}</div>',
        "</body>",
        "</html>",
    ])

    return "\n".join(lines) + "\n"


def save_changelog(
    month_year: str, markdown: str, html: str
) -> tuple[Path, Path, Path]:
    """Save changelog to output/changelogs/ and docs/changelogs/.

    Returns (md_path, html_output_path, html_docs_path).
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    md_path = OUTPUT_DIR / f"{month_year}.md"
    html_output_path = OUTPUT_DIR / f"{month_year}.html"
    html_docs_path = DOCS_DIR / f"{month_year}.html"

    md_path.write_text(markdown)
    html_output_path.write_text(html)
    html_docs_path.write_text(html)

    logger.info("Saved changelog: %s, %s, %s", md_path, html_output_path, html_docs_path)
    return md_path, html_output_path, html_docs_path


def save_index(index_html: str) -> Path:
    """Save the index page to docs/index.html."""
    docs_root = PROJECT_ROOT / "docs"
    docs_root.mkdir(parents=True, exist_ok=True)
    index_path = docs_root / "index.html"
    index_path.write_text(index_html)
    logger.info("Saved changelog index: %s", index_path)
    return index_path
