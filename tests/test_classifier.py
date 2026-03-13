"""Tests for the classifier module — AI-powered item classification."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.processor.classifier import (
    _build_prompt,
    _parse_classification,
    classify_items,
)


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_basic_prompt_formatting(self):
        item = {
            "title": "feat: add new API",
            "repo": "aptos-labs/aptos-core",
            "source_type": "pr",
            "body": "This PR adds a new API endpoint.",
        }
        prompt = _build_prompt(item)
        assert "feat: add new API" in prompt
        assert "aptos-labs/aptos-core" in prompt
        assert "pr" in prompt
        assert "This PR adds a new API endpoint." in prompt

    def test_missing_fields_default_to_empty(self):
        item = {"id": "1"}
        prompt = _build_prompt(item)
        assert "Title: \n" in prompt
        assert "Repo: \n" in prompt
        assert "Type: \n" in prompt

    def test_body_truncated_at_500_chars(self):
        item = {
            "title": "test",
            "repo": "r",
            "source_type": "pr",
            "body": "x" * 1000,
        }
        prompt = _build_prompt(item)
        # The body in the prompt should be at most 500 chars
        body_start = prompt.index("Description: ") + len("Description: ")
        body_in_prompt = prompt[body_start:prompt.index("\n\nClassification rules:")]
        assert len(body_in_prompt) == 500

    def test_none_body_handled(self):
        item = {"title": "test", "repo": "r", "source_type": "pr", "body": None}
        prompt = _build_prompt(item)
        assert "Description: \n" in prompt


# ---------------------------------------------------------------------------
# _parse_classification
# ---------------------------------------------------------------------------


class TestParseClassification:
    def test_valid_response(self):
        raw = json.dumps({
            "category": "dev-facing",
            "audience": ["sdk-users", "dapp-developers"],
            "one_liner": "New SDK method for transaction simulation",
        })
        result = _parse_classification(raw)
        assert result is not None
        assert result["category"] == "dev-facing"
        assert result["audience"] == ["sdk-users", "dapp-developers"]
        assert result["one_liner"] == "New SDK method for transaction simulation"

    def test_breaking_category(self):
        raw = json.dumps({
            "category": "breaking",
            "audience": ["sdk-users"],
            "one_liner": "API endpoint removed",
        })
        result = _parse_classification(raw)
        assert result is not None
        assert result["category"] == "breaking"

    def test_node_operator_category(self):
        raw = json.dumps({
            "category": "node-operator",
            "audience": ["node-operators"],
            "one_liner": "Consensus parameter change",
        })
        result = _parse_classification(raw)
        assert result is not None
        assert result["category"] == "node-operator"

    def test_internal_category(self):
        raw = json.dumps({
            "category": "internal",
            "audience": [],
            "one_liner": "Refactored test utils",
        })
        result = _parse_classification(raw)
        assert result is not None
        assert result["category"] == "internal"

    def test_invalid_category_returns_none(self):
        raw = json.dumps({"category": "unknown", "audience": [], "one_liner": ""})
        result = _parse_classification(raw)
        assert result is None

    def test_invalid_json_returns_none(self):
        result = _parse_classification("not json at all")
        assert result is None

    def test_empty_string_returns_none(self):
        result = _parse_classification("")
        assert result is None

    def test_markdown_wrapped_json_returns_none(self):
        raw = '```json\n{"category": "internal", "audience": [], "one_liner": ""}\n```'
        result = _parse_classification(raw)
        assert result is None

    def test_invalid_audience_values_filtered(self):
        raw = json.dumps({
            "category": "dev-facing",
            "audience": ["sdk-users", "invalid-audience", "move-developers"],
            "one_liner": "Test",
        })
        result = _parse_classification(raw)
        assert result is not None
        assert result["audience"] == ["sdk-users", "move-developers"]

    def test_audience_as_string_coerced_to_list(self):
        raw = json.dumps({
            "category": "dev-facing",
            "audience": "sdk-users",
            "one_liner": "Test",
        })
        result = _parse_classification(raw)
        assert result is not None
        assert result["audience"] == ["sdk-users"]

    def test_non_string_one_liner_defaults_to_empty(self):
        raw = json.dumps({
            "category": "dev-facing",
            "audience": [],
            "one_liner": 123,
        })
        result = _parse_classification(raw)
        assert result is not None
        assert result["one_liner"] == ""


# ---------------------------------------------------------------------------
# classify_items
# ---------------------------------------------------------------------------


class TestClassifyItems:
    """Test the public classify_items() function."""

    SAMPLE_ITEMS = [
        {"id": "1", "title": "feat!: remove deprecated API", "repo": "aptos-labs/aptos-core", "source_type": "pr", "body": "Removes the old v1 API."},
        {"id": "2", "title": "fix: transaction simulation timeout", "repo": "aptos-labs/aptos-ts-sdk", "source_type": "pr", "body": "Fixes timeout in simulate()."},
        {"id": "3", "title": "[storage] Refactor RocksDB compaction", "repo": "aptos-labs/aptos-core", "source_type": "pr", "body": "Internal storage refactor."},
        {"id": "4", "title": "chore: update CI scripts", "repo": "aptos-labs/aptos-core", "source_type": "pr", "body": "CI configuration changes."},
    ]

    def test_empty_items_returns_empty(self):
        result = classify_items([])
        assert result == []

    def test_skip_classify_returns_all_items(self):
        with patch.dict("os.environ", {"SKIP_CLASSIFY": "true"}):
            result = classify_items(self.SAMPLE_ITEMS)
        assert len(result) == 4

    def test_skip_classify_case_insensitive(self):
        with patch.dict("os.environ", {"SKIP_CLASSIFY": "TRUE"}):
            result = classify_items(self.SAMPLE_ITEMS)
        assert len(result) == 4

    def test_skip_classify_with_1(self):
        with patch.dict("os.environ", {"SKIP_CLASSIFY": "1"}):
            result = classify_items(self.SAMPLE_ITEMS)
        assert len(result) == 4

    def test_skip_classify_with_yes(self):
        with patch.dict("os.environ", {"SKIP_CLASSIFY": "yes"}):
            result = classify_items(self.SAMPLE_ITEMS)
        assert len(result) == 4

    def test_skip_classify_not_set_proceeds(self):
        """When SKIP_CLASSIFY is not set, classification should proceed (and we mock the API)."""
        mock_results = {
            "1": {"category": "breaking", "audience": ["sdk-users"], "one_liner": "Deprecated API removed"},
            "2": {"category": "dev-facing", "audience": ["sdk-users"], "one_liner": "Fixed simulation timeout"},
            "3": {"category": "node-operator", "audience": ["node-operators"], "one_liner": "Storage refactor"},
            "4": {"category": "internal", "audience": [], "one_liner": "CI update"},
        }
        with (
            patch.dict("os.environ", {}, clear=False),
            patch("src.processor.classifier._create_client") as mock_client,
            patch("src.processor.classifier._classify_via_batch", return_value=mock_results),
        ):
            # Remove SKIP_CLASSIFY if present
            import os
            os.environ.pop("SKIP_CLASSIFY", None)
            result = classify_items(self.SAMPLE_ITEMS)

        # Should only keep breaking and dev-facing
        assert len(result) == 2
        ids = [item["id"] for item in result]
        assert "1" in ids
        assert "2" in ids
        assert "3" not in ids
        assert "4" not in ids

    def test_classification_fields_attached(self):
        mock_results = {
            "1": {"category": "breaking", "audience": ["sdk-users"], "one_liner": "API removed"},
        }
        items = [self.SAMPLE_ITEMS[0]]
        with (
            patch.dict("os.environ", {}, clear=False),
            patch("src.processor.classifier._create_client"),
            patch("src.processor.classifier._classify_via_batch", return_value=mock_results),
        ):
            import os
            os.environ.pop("SKIP_CLASSIFY", None)
            result = classify_items(items)

        assert len(result) == 1
        assert result[0]["category"] == "breaking"
        assert result[0]["audience"] == ["sdk-users"]
        assert result[0]["one_liner"] == "API removed"
        # Original fields preserved
        assert result[0]["title"] == "feat!: remove deprecated API"

    def test_unclassified_items_dropped(self):
        """Items missing from batch results default to internal and are dropped."""
        mock_results = {
            "1": {"category": "dev-facing", "audience": ["sdk-users"], "one_liner": "Test"},
            # items 2, 3, 4 missing from results
        }
        with (
            patch.dict("os.environ", {}, clear=False),
            patch("src.processor.classifier._create_client"),
            patch("src.processor.classifier._classify_via_batch", return_value=mock_results),
        ):
            import os
            os.environ.pop("SKIP_CLASSIFY", None)
            result = classify_items(self.SAMPLE_ITEMS)

        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_batch_failure_returns_all_items(self):
        """If the entire batch fails, return all items unclassified."""
        with (
            patch.dict("os.environ", {}, clear=False),
            patch("src.processor.classifier._create_client", side_effect=RuntimeError("API down")),
        ):
            import os
            os.environ.pop("SKIP_CLASSIFY", None)
            result = classify_items(self.SAMPLE_ITEMS)

        # All items returned unmodified as fallback
        assert len(result) == 4

    def test_does_not_mutate_input(self):
        mock_results = {
            "1": {"category": "breaking", "audience": ["sdk-users"], "one_liner": "Test"},
        }
        items = [dict(self.SAMPLE_ITEMS[0])]
        original_keys = set(items[0].keys())
        with (
            patch.dict("os.environ", {}, clear=False),
            patch("src.processor.classifier._create_client"),
            patch("src.processor.classifier._classify_via_batch", return_value=mock_results),
        ):
            import os
            os.environ.pop("SKIP_CLASSIFY", None)
            classify_items(items)

        # Original item should not have classification fields
        assert set(items[0].keys()) == original_keys
