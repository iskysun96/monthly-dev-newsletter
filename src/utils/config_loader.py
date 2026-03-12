"""YAML configuration loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def load_yaml(filename: str) -> dict[str, Any]:
    """Load a YAML config file from the config directory."""
    path = CONFIG_DIR / filename
    with open(path) as f:
        return yaml.safe_load(f)


def load_repos_config() -> dict[str, Any]:
    return load_yaml("repos.yaml")


def load_sources_config() -> dict[str, Any]:
    return load_yaml("sources.yaml")


def load_newsletter_config() -> dict[str, Any]:
    return load_yaml("newsletter.yaml")
