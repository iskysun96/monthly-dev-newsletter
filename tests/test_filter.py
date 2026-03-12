"""Tests for the filter module — noise removal before categorization."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.processor.filter import (
    filter_items,
    _compile_patterns,
    _compile_title_patterns,
    _matches_any,
    _title_matches_any,
)


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestCompilePatterns:
    def test_valid_patterns_compile(self):
        patterns = _compile_patterns([r"^feat", r"(?i)^bump"])
        assert len(patterns) == 2

    def test_invalid_pattern_skipped(self):
        patterns = _compile_patterns([r"^feat", r"[invalid", r"^fix"])
        assert len(patterns) == 2

    def test_empty_list(self):
        patterns = _compile_patterns([])
        assert patterns == []


class TestCompileTitlePatterns:
    def test_plain_strings(self):
        patterns = _compile_title_patterns([r"^feat", r"^fix"])
        assert len(patterns) == 2
        assert patterns[0].except_repos == []

    def test_dict_with_except_repos(self):
        patterns = _compile_title_patterns([
            {"pattern": r"^docs", "except_repos": ["aptos-labs/aptos-docs"]},
        ])
        assert len(patterns) == 1
        assert patterns[0].except_repos == ["aptos-labs/aptos-docs"]

    def test_mixed_entries(self):
        patterns = _compile_title_patterns([
            r"^chore",
            {"pattern": r"^docs", "except_repos": ["repo-a"]},
        ])
        assert len(patterns) == 2
        assert patterns[0].except_repos == []
        assert patterns[1].except_repos == ["repo-a"]

    def test_invalid_pattern_skipped(self):
        patterns = _compile_title_patterns([r"[invalid", r"^feat"])
        assert len(patterns) == 1


class TestTitleMatchesAny:
    def test_matches_plain_pattern(self):
        patterns = _compile_title_patterns([r"^docs"])
        assert _title_matches_any("docs: fix README", patterns, "some/repo") is True

    def test_except_repo_skips_match(self):
        patterns = _compile_title_patterns([
            {"pattern": r"^docs", "except_repos": ["aptos-labs/aptos-docs"]},
        ])
        assert _title_matches_any("docs: update guide", patterns, "aptos-labs/aptos-docs") is False

    def test_non_exempt_repo_still_filtered(self):
        patterns = _compile_title_patterns([
            {"pattern": r"^docs", "except_repos": ["aptos-labs/aptos-docs"]},
        ])
        assert _title_matches_any("docs: update guide", patterns, "aptos-labs/aptos-core") is True

    def test_no_match_returns_false(self):
        patterns = _compile_title_patterns([r"^docs"])
        assert _title_matches_any("feat: new feature", patterns, "some/repo") is False


class TestMatchesAny:
    def test_matches_first_pattern(self):
        patterns = _compile_patterns([r"^chore", r"^docs"])
        assert _matches_any("chore: update deps", patterns) is True

    def test_matches_second_pattern(self):
        patterns = _compile_patterns([r"^chore", r"^docs"])
        assert _matches_any("docs: fix README", patterns) is True

    def test_no_match(self):
        patterns = _compile_patterns([r"^chore", r"^docs"])
        assert _matches_any("feat: new API", patterns) is False


# ---------------------------------------------------------------------------
# filter_items
# ---------------------------------------------------------------------------


class TestFilterItems:
    """Test the public filter_items() function."""

    SAMPLE_CONFIG = {
        "filtering": {
            "exclude_title_patterns": [
                r"^chore[:(]",
                {
                    "pattern": r"^docs[:(]",
                    "except_repos": [
                        "aptos-labs/aptos-docs",
                        "aptos-labs/move-by-examples",
                    ],
                },
                r"^ci[:(]",
                r"^build[:(]",
                r"^test[:(]",
                r"^style[:(]",
                r"^refactor[:(]",
                r"^Version Packages$",
                r"(?i)^bump version",
                r"(?i)^republish",
                r"(?i)^re-?release",
                r"^\[cp\]",
                r"(?i)^cherry-?pick",
                r"(?i)^backport",
                r"^\[release\]",
            ],
            "exclude_label_patterns": [
                "cherry-pick",
                "backport",
            ],
            "exclude_prerelease": True,
        },
    }

    def test_chore_prefix_excluded(self):
        items = [
            {"id": "1", "title": "chore: update deps"},
            {"id": "2", "title": "feat: new API"},
        ]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 1
        assert result[0]["id"] == "2"

    def test_docs_prefix_excluded(self):
        items = [{"id": "1", "title": "docs: fix README", "repo": "aptos-labs/aptos-core"}]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 0

    def test_docs_prefix_kept_for_exempt_repo_aptos_docs(self):
        items = [{"id": "1", "title": "docs: update quickstart guide", "repo": "aptos-labs/aptos-docs"}]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_docs_prefix_kept_for_exempt_repo_move_by_examples(self):
        items = [{"id": "1", "title": "docs(move): add new example", "repo": "aptos-labs/move-by-examples"}]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_ci_prefix_excluded(self):
        items = [{"id": "1", "title": "ci: update workflow"}]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 0

    def test_version_packages_excluded(self):
        items = [{"id": "1", "title": "Version Packages"}]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 0

    def test_bump_version_excluded(self):
        items = [{"id": "1", "title": "bump version to 0.3.0"}]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 0

    def test_republish_excluded(self):
        items = [{"id": "1", "title": "republish with correct build"}]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 0

    def test_cp_cherry_pick_excluded(self):
        items = [
            {"id": "1", "title": "[cp][aptos-release-v1.40] fix gas"},
            {"id": "2", "title": "[cp][aptos-release-v1.41] storage patch"},
            {"id": "3", "title": "[cp][aptos-release-v1.42] consensus fix"},
        ]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 0

    def test_cherry_pick_prefix_excluded(self):
        items = [{"id": "1", "title": "cherry-pick fix from main"}]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 0

    def test_backport_prefix_excluded(self):
        items = [{"id": "1", "title": "backport: fix for v1.3"}]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 0

    def test_release_prefix_excluded(self):
        items = [{"id": "1", "title": "[release] 6.2.0"}]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 0

    def test_label_based_exclusion_cherry_pick(self):
        items = [
            {"id": "1", "title": "fix gas calculation", "labels": ["cherry-pick", "gas"]},
        ]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 0

    def test_label_based_exclusion_backport(self):
        items = [
            {"id": "1", "title": "update storage layer", "labels": ["backport"]},
        ]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 0

    def test_prerelease_filtered(self):
        items = [
            {"id": "1", "title": "v2.0.0-rc1", "prerelease": True},
            {"id": "2", "title": "v2.0.0", "prerelease": False},
        ]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 1
        assert result[0]["id"] == "2"

    def test_non_matching_items_kept(self):
        items = [
            {"id": "1", "title": "feat: add Move module support"},
            {"id": "2", "title": "[consensus] Remove randomness fast path"},
            {"id": "3", "title": "AIP-77: Gas Schedule V2"},
        ]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 3

    def test_empty_config_returns_all(self):
        items = [
            {"id": "1", "title": "chore: update deps"},
            {"id": "2", "title": "feat: new API"},
        ]
        result = filter_items(items, config={})
        assert len(result) == 2

    def test_empty_filtering_section_returns_all(self):
        items = [
            {"id": "1", "title": "chore: update deps"},
        ]
        result = filter_items(items, config={"filtering": {}})
        assert len(result) == 1

    def test_invalid_regex_skipped_gracefully(self):
        config = {
            "filtering": {
                "exclude_title_patterns": [r"[invalid", r"^chore"],
                "exclude_label_patterns": [],
                "exclude_prerelease": False,
            },
        }
        items = [
            {"id": "1", "title": "chore: update deps"},
            {"id": "2", "title": "feat: new API"},
        ]
        result = filter_items(items, config=config)
        # Invalid regex skipped, but ^chore still works
        assert len(result) == 1
        assert result[0]["id"] == "2"

    def test_does_not_mutate_input(self):
        items = [
            {"id": "1", "title": "chore: update deps"},
            {"id": "2", "title": "feat: new API"},
        ]
        original_len = len(items)
        filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(items) == original_len

    def test_items_without_labels_not_crashed(self):
        """Items missing the 'labels' key should not cause errors."""
        items = [{"id": "1", "title": "feat: something"}]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 1

    def test_loads_config_automatically_when_none(self):
        items = [{"id": "1", "title": "feat: test"}]
        mock_config = {"filtering": {}}
        with patch("src.processor.filter.load_newsletter_config", return_value=mock_config):
            result = filter_items(items)
        assert len(result) == 1

    def test_case_insensitive_bump_version(self):
        items = [{"id": "1", "title": "Bump version to 1.0.0"}]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 0

    def test_case_insensitive_republish(self):
        items = [{"id": "1", "title": "Republish with correct build"}]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 0

    def test_rerelease_with_hyphen(self):
        items = [{"id": "1", "title": "re-release v1.0"}]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 0

    def test_rerelease_without_hyphen(self):
        items = [{"id": "1", "title": "rerelease v1.0"}]
        result = filter_items(items, config=self.SAMPLE_CONFIG)
        assert len(result) == 0
