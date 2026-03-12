"""Tests for the categorizer module — rule matching and section assignment."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.processor.categorizer import (
    _match_contains,
    _match_contains_any,
    _match_equals,
    _match_pattern,
    _rule_matches,
    _section_matches,
    categorize,
)


# ---------------------------------------------------------------------------
# Individual rule matchers
# ---------------------------------------------------------------------------


class TestMatchPattern:
    def test_string_match(self):
        assert _match_pattern("feat: add move module", r"^feat") is True

    def test_string_no_match(self):
        assert _match_pattern("chore: update deps", r"^feat") is False

    def test_list_match(self):
        assert _match_pattern(["alpha", "beta"], r"bet") is True

    def test_list_no_match(self):
        assert _match_pattern(["alpha", "gamma"], r"bet") is False

    def test_none_value(self):
        assert _match_pattern(None, r"anything") is False

    def test_case_insensitive_via_pattern(self):
        assert _match_pattern("BREAKING CHANGE", r"(?i)breaking") is True


class TestMatchContains:
    def test_substring_in_string(self):
        assert _match_contains("hello world", "world") is True

    def test_substring_not_in_string(self):
        assert _match_contains("hello world", "mars") is False

    def test_membership_in_list(self):
        assert _match_contains(["sdk", "tooling"], "sdk") is True

    def test_not_member_in_list(self):
        assert _match_contains(["sdk", "tooling"], "consensus") is False

    def test_none_value(self):
        assert _match_contains(None, "anything") is False

    def test_partial_match_not_in_list(self):
        """List membership is exact, not substring."""
        assert _match_contains(["sdk-core"], "sdk") is False


class TestMatchContainsAny:
    def test_any_match_in_list(self):
        assert _match_contains_any(
            ["sdk", "tooling", "cli"],
            ["cli", "indexer"],
        ) is True

    def test_no_match_in_list(self):
        assert _match_contains_any(
            ["sdk", "tooling"],
            ["consensus", "execution"],
        ) is False

    def test_any_match_in_string(self):
        assert _match_contains_any(
            "this is about sdk development",
            ["sdk", "tooling"],
        ) is True

    def test_none_value(self):
        assert _match_contains_any(None, ["anything"]) is False

    def test_empty_candidates(self):
        assert _match_contains_any(["sdk"], []) is False


class TestMatchEquals:
    def test_string_equality(self):
        assert _match_equals("release", "release") is True

    def test_string_inequality(self):
        assert _match_equals("release", "pr") is False

    def test_list_contains_exact(self):
        assert _match_equals(["alpha", "beta"], "beta") is True

    def test_list_does_not_contain(self):
        assert _match_equals(["alpha", "beta"], "gamma") is False

    def test_none_value(self):
        assert _match_equals(None, "anything") is False

    def test_numeric_converted_to_string(self):
        assert _match_equals(42, "42") is True


# ---------------------------------------------------------------------------
# _rule_matches
# ---------------------------------------------------------------------------


class TestRuleMatches:
    def test_catch_all_always_matches(self):
        rule = {"catch_all": True}
        item = {"id": "anything", "source_type": "blog"}
        assert _rule_matches(rule, item) is True

    def test_type_rule_matches(self):
        rule = {"type": "release"}
        item = {"id": "r1", "source_type": "release"}
        assert _rule_matches(rule, item) is True

    def test_type_rule_does_not_match(self):
        rule = {"type": "release"}
        item = {"id": "p1", "source_type": "pr"}
        assert _rule_matches(rule, item) is False

    def test_field_pattern_rule(self):
        rule = {"field": "title", "pattern": r"^feat"}
        item = {"id": "i1", "title": "feat: new API"}
        assert _rule_matches(rule, item) is True

    def test_field_contains_rule(self):
        rule = {"field": "labels", "contains": "breaking-change"}
        item = {"id": "i1", "labels": ["breaking-change", "api"]}
        assert _rule_matches(rule, item) is True

    def test_field_contains_any_rule(self):
        rule = {"field": "labels", "contains_any": ["consensus", "execution"]}
        item = {"id": "i1", "labels": ["execution", "performance"]}
        assert _rule_matches(rule, item) is True

    def test_field_equals_rule(self):
        rule = {"field": "source_type", "equals": "aip"}
        item = {"id": "a1", "source_type": "aip"}
        assert _rule_matches(rule, item) is True

    def test_combined_type_and_field_both_must_match(self):
        """When type and field conditions are combined, both must match."""
        rule = {"type": "release", "field": "repo", "pattern": "aptos-core"}
        item_match = {"id": "r1", "source_type": "release", "repo": "aptos-labs/aptos-core"}
        item_wrong_type = {"id": "p1", "source_type": "pr", "repo": "aptos-labs/aptos-core"}
        item_wrong_repo = {"id": "r2", "source_type": "release", "repo": "aptos-labs/sdk"}

        assert _rule_matches(rule, item_match) is True
        assert _rule_matches(rule, item_wrong_type) is False
        assert _rule_matches(rule, item_wrong_repo) is False

    def test_rule_with_no_conditions_matches(self):
        """A rule with no catch_all, no type, and no field is vacuously true."""
        rule = {}
        item = {"id": "x"}
        assert _rule_matches(rule, item) is True


# ---------------------------------------------------------------------------
# _section_matches
# ---------------------------------------------------------------------------


class TestSectionMatches:
    def test_section_with_no_rules_does_not_match(self):
        section = {"id": "empty", "rules": []}
        item = {"id": "x"}
        assert _section_matches(section, item) is False

    def test_any_rule_matching_makes_section_match(self):
        """Section rules are OR-ed: if any rule matches, the section matches."""
        section = {
            "id": "test",
            "rules": [
                {"field": "title", "pattern": "^WONTMATCH$"},
                {"field": "source_type", "equals": "blog"},
            ],
        }
        item = {"id": "b1", "source_type": "blog", "title": "Hello"}
        assert _section_matches(section, item) is True


# ---------------------------------------------------------------------------
# categorize (integration)
# ---------------------------------------------------------------------------


class TestCategorize:
    """Test the public categorize() function with a test config."""

    SAMPLE_CONFIG = {
        "sections": [
            {
                "id": "breaking",
                "title": "Breaking Changes",
                "priority": 1,
                "rules": [
                    {"field": "title", "pattern": r"(?i)break(ing)?"},
                    {"field": "labels", "contains": "breaking-change"},
                ],
            },
            {
                "id": "releases",
                "title": "Releases",
                "priority": 2,
                "rules": [
                    {"type": "release"},
                ],
            },
            {
                "id": "aips",
                "title": "AIPs",
                "priority": 3,
                "rules": [
                    {"field": "source_type", "equals": "aip"},
                ],
            },
            {
                "id": "community",
                "title": "Community",
                "priority": 10,
                "rules": [
                    {"catch_all": True},
                ],
            },
        ]
    }

    def test_items_assigned_to_correct_sections(self):
        items = [
            {"id": "r1", "source_type": "release", "title": "v1.0.0 Released"},
            {"id": "a1", "source_type": "aip", "title": "AIP-42: New Standard"},
            {"id": "b1", "source_type": "blog", "title": "Community Update"},
        ]

        result = categorize(items, config=self.SAMPLE_CONFIG)

        assert len(result["releases"]) == 1
        assert result["releases"][0]["id"] == "r1"
        assert len(result["aips"]) == 1
        assert result["aips"][0]["id"] == "a1"
        assert len(result["community"]) == 1
        assert result["community"][0]["id"] == "b1"

    def test_priority_ordering_higher_priority_claims_first(self):
        """An item matching both 'breaking' and 'releases' goes to 'breaking'
        because it has a lower priority number (higher actual priority)."""
        items = [
            {
                "id": "br1",
                "source_type": "release",
                "title": "BREAKING: v2.0.0",
                "labels": [],
            },
        ]

        result = categorize(items, config=self.SAMPLE_CONFIG)

        # Should be in 'breaking' (priority 1), not 'releases' (priority 2)
        assert len(result["breaking"]) == 1
        assert result["breaking"][0]["id"] == "br1"
        assert len(result["releases"]) == 0

    def test_catch_all_collects_unmatched_items(self):
        """Items not claimed by specific sections fall into the catch_all."""
        items = [
            {"id": "f1", "source_type": "forum", "title": "Forum discussion"},
            {"id": "f2", "source_type": "forum", "title": "Another forum post"},
        ]

        result = categorize(items, config=self.SAMPLE_CONFIG)

        assert len(result["community"]) == 2

    def test_items_only_appear_in_one_section(self):
        """Each item must appear in exactly one section — no duplicates across sections."""
        items = [
            {"id": "r1", "source_type": "release", "title": "BREAKING: v2.0.0"},
            {"id": "a1", "source_type": "aip", "title": "AIP-10"},
            {"id": "b1", "source_type": "blog", "title": "Blog post"},
            {"id": "b2", "source_type": "blog", "title": "Another breaking blog"},
        ]

        result = categorize(items, config=self.SAMPLE_CONFIG)

        all_assigned_ids = []
        for section_items in result.values():
            all_assigned_ids.extend(item["id"] for item in section_items)

        # No duplicates
        assert len(all_assigned_ids) == len(set(all_assigned_ids))
        # All items assigned (because catch_all exists)
        assert len(all_assigned_ids) == len(items)

    def test_pattern_rule(self):
        """Pattern rule uses regex search."""
        items = [
            {"id": "x1", "source_type": "pr", "title": "feat!: breaking API change"},
        ]
        config = {
            "sections": [
                {
                    "id": "breaking",
                    "title": "Breaking",
                    "priority": 1,
                    "rules": [{"field": "title", "pattern": r"^(feat|fix)!:"}],
                },
            ]
        }
        result = categorize(items, config=config)
        assert len(result["breaking"]) == 1

    def test_contains_rule(self):
        items = [
            {"id": "x1", "source_type": "pr", "labels": ["consensus", "performance"]},
        ]
        config = {
            "sections": [
                {
                    "id": "protocol",
                    "title": "Protocol",
                    "priority": 1,
                    "rules": [{"field": "labels", "contains": "consensus"}],
                },
            ]
        }
        result = categorize(items, config=config)
        assert len(result["protocol"]) == 1

    def test_contains_any_rule(self):
        items = [
            {"id": "x1", "source_type": "pr", "labels": ["storage", "cleanup"]},
        ]
        config = {
            "sections": [
                {
                    "id": "protocol",
                    "title": "Protocol",
                    "priority": 1,
                    "rules": [
                        {
                            "field": "labels",
                            "contains_any": ["consensus", "execution", "storage"],
                        }
                    ],
                },
            ]
        }
        result = categorize(items, config=config)
        assert len(result["protocol"]) == 1

    def test_equals_rule(self):
        items = [
            {"id": "a1", "source_type": "aip", "title": "AIP-1"},
        ]
        config = {
            "sections": [
                {
                    "id": "aips",
                    "title": "AIPs",
                    "priority": 1,
                    "rules": [{"field": "source_type", "equals": "aip"}],
                },
            ]
        }
        result = categorize(items, config=config)
        assert len(result["aips"]) == 1

    def test_empty_items_returns_empty_sections(self):
        result = categorize([], config=self.SAMPLE_CONFIG)

        for section_id in ["breaking", "releases", "aips", "community"]:
            assert result[section_id] == []

    def test_all_section_ids_present_in_result(self):
        """Even sections with no matching items appear in the result dict."""
        result = categorize([], config=self.SAMPLE_CONFIG)

        assert set(result.keys()) == {"breaking", "releases", "aips", "community"}

    def test_loads_config_automatically_when_none(self):
        """When config=None, categorize calls load_newsletter_config."""
        items = [{"id": "x", "source_type": "blog", "title": "Test"}]

        mock_config = {
            "sections": [
                {
                    "id": "all",
                    "title": "All",
                    "priority": 1,
                    "rules": [{"catch_all": True}],
                },
            ]
        }

        with patch("src.processor.categorizer.load_newsletter_config", return_value=mock_config):
            result = categorize(items)

        assert len(result["all"]) == 1


# ---------------------------------------------------------------------------
# Expanded categorization rules — bracket-prefix titles
# ---------------------------------------------------------------------------


class TestExpandedCategorizationRules:
    """Test that real aptos-core PR title conventions categorize correctly."""

    CONFIG_WITH_EXPANDED_RULES = {
        "sections": [
            {
                "id": "breaking_changes",
                "title": "Breaking Changes",
                "priority": 1,
                "rules": [
                    {"field": "title", "pattern": r"(?i)break(ing)?|BREAKING"},
                    {"field": "labels", "contains": "breaking-change"},
                    {"field": "title", "pattern": r"^(feat|fix)!:"},
                ],
            },
            {
                "id": "protocol_updates",
                "title": "Protocol Updates",
                "priority": 2,
                "rules": [
                    {"field": "repo", "pattern": "aptos-core", "type": "release"},
                    {"field": "labels", "contains_any": ["consensus", "execution", "storage", "mempool", "state-sync"]},
                    {"field": "title", "pattern": r"(?i)^\[(consensus|execution|storage|mempool|state-sync|gas|network|compiler[^\]]*|dkg|validator|vm|api|indexer|move[^\]]*)\]"},
                ],
            },
            {
                "id": "new_features",
                "title": "New Features",
                "priority": 4,
                "rules": [
                    {"field": "title", "pattern": r"^feat[:(]"},
                    {"field": "labels", "contains_any": ["enhancement", "feature"]},
                    {"field": "title", "pattern": r"(?i)(add(ing|s)?\s+(support|new)|introduc(e|ing)|new feature)"},
                ],
            },
            {
                "id": "community",
                "title": "Community",
                "priority": 10,
                "rules": [{"catch_all": True}],
            },
        ]
    }

    def test_consensus_bracket_to_protocol_updates(self):
        items = [
            {"id": "p1", "source_type": "pr", "title": "[consensus] Remove randomness fast path code", "labels": []},
        ]
        result = categorize(items, config=self.CONFIG_WITH_EXPANDED_RULES)
        assert len(result["protocol_updates"]) == 1
        assert result["protocol_updates"][0]["id"] == "p1"

    def test_storage_bracket_to_protocol_updates(self):
        items = [
            {"id": "p2", "source_type": "pr", "title": "[storage] Remove dead StateValueSchema from DB", "labels": []},
        ]
        result = categorize(items, config=self.CONFIG_WITH_EXPANDED_RULES)
        assert len(result["protocol_updates"]) == 1

    def test_gas_bracket_to_protocol_updates(self):
        items = [
            {"id": "p3", "source_type": "pr", "title": "[gas] Apply 10x multiplier to gas schedule", "labels": []},
        ]
        result = categorize(items, config=self.CONFIG_WITH_EXPANDED_RULES)
        assert len(result["protocol_updates"]) == 1

    def test_compiler_v2_bracket_to_protocol_updates(self):
        items = [
            {"id": "p4", "source_type": "pr", "title": "[compiler-v2] Fix type inference for closures", "labels": []},
        ]
        result = categorize(items, config=self.CONFIG_WITH_EXPANDED_RULES)
        assert len(result["protocol_updates"]) == 1

    def test_network_bracket_to_protocol_updates(self):
        items = [
            {"id": "p5", "source_type": "pr", "title": "[Network] Add priority inbound peer support", "labels": []},
        ]
        result = categorize(items, config=self.CONFIG_WITH_EXPANDED_RULES)
        assert len(result["protocol_updates"]) == 1

    def test_move_bracket_to_protocol_updates(self):
        items = [
            {"id": "p6", "source_type": "pr", "title": "[move flow] adding supports for unit test generation", "labels": []},
        ]
        result = categorize(items, config=self.CONFIG_WITH_EXPANDED_RULES)
        assert len(result["protocol_updates"]) == 1

    def test_vm_bracket_to_protocol_updates(self):
        items = [
            {"id": "p7", "source_type": "pr", "title": "[vm] Optimize module loading", "labels": []},
        ]
        result = categorize(items, config=self.CONFIG_WITH_EXPANDED_RULES)
        assert len(result["protocol_updates"]) == 1

    def test_dkg_bracket_to_protocol_updates(self):
        items = [
            {"id": "p8", "source_type": "pr", "title": "[dkg] Update DKG threshold", "labels": []},
        ]
        result = categorize(items, config=self.CONFIG_WITH_EXPANDED_RULES)
        assert len(result["protocol_updates"]) == 1

    def test_feat_prefix_to_new_features(self):
        items = [
            {"id": "f1", "source_type": "pr", "title": "feat: add CLI flags for verbose mode", "labels": []},
        ]
        result = categorize(items, config=self.CONFIG_WITH_EXPANDED_RULES)
        assert len(result["new_features"]) == 1

    def test_adding_support_to_new_features(self):
        items = [
            {"id": "f2", "source_type": "pr", "title": "Adding support for new transaction types", "labels": []},
        ]
        result = categorize(items, config=self.CONFIG_WITH_EXPANDED_RULES)
        assert len(result["new_features"]) == 1

    def test_introduce_to_new_features(self):
        items = [
            {"id": "f3", "source_type": "pr", "title": "Introduce batch API endpoints", "labels": []},
        ]
        result = categorize(items, config=self.CONFIG_WITH_EXPANDED_RULES)
        assert len(result["new_features"]) == 1

    def test_add_new_to_new_features(self):
        items = [
            {"id": "f4", "source_type": "pr", "title": "Add new signing scheme for Ed25519", "labels": []},
        ]
        result = categorize(items, config=self.CONFIG_WITH_EXPANDED_RULES)
        assert len(result["new_features"]) == 1

    def test_unmatched_item_falls_to_community(self):
        items = [
            {"id": "c1", "source_type": "blog", "title": "Aptos ecosystem recap", "labels": []},
        ]
        result = categorize(items, config=self.CONFIG_WITH_EXPANDED_RULES)
        assert len(result["community"]) == 1

    def test_breaking_consensus_goes_to_breaking(self):
        """Breaking changes have higher priority than protocol updates."""
        items = [
            {"id": "bc1", "source_type": "pr", "title": "[consensus] BREAKING: new epoch format", "labels": []},
        ]
        result = categorize(items, config=self.CONFIG_WITH_EXPANDED_RULES)
        assert len(result["breaking_changes"]) == 1
        assert len(result["protocol_updates"]) == 0
