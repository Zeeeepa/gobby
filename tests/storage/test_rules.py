"""Tests for rules storage module (three-tier rule registry).

Covers: table creation via migration, save_rule with all tiers,
get_rule by name with tier precedence (project > user > bundled),
list_rules with tier filter, delete_rule, unique constraint enforcement.
"""

from __future__ import annotations

import json
import uuid

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.rules import RuleStore

pytestmark = pytest.mark.unit


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def rule_store(temp_db: LocalDatabase) -> RuleStore:
    """Create a RuleStore backed by the temp database."""
    return RuleStore(temp_db)


@pytest.fixture
def project_id(temp_db: LocalDatabase) -> str:
    """Create a test project and return its ID."""
    pid = str(uuid.uuid4())
    temp_db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        (pid, f"test-project-{pid[:8]}"),
    )
    return pid


# =============================================================================
# Table existence
# =============================================================================


class TestRulesTableExists:
    def test_rules_table_created_by_migration(self, temp_db: LocalDatabase) -> None:
        """The rules table should exist after migrations run."""
        row = temp_db.fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name='rules'")
        assert row is not None
        assert row["name"] == "rules"

    def test_unique_constraint_exists(self, temp_db: LocalDatabase) -> None:
        """UNIQUE(name, tier, project_id) should be enforced."""
        import sqlite3

        rule_id_1 = str(uuid.uuid4())
        rule_id_2 = str(uuid.uuid4())
        definition = json.dumps({"tools": ["Edit"], "reason": "test", "action": "block"})

        temp_db.execute(
            """INSERT INTO rules (id, name, tier, project_id, definition, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (rule_id_1, "no_push", "bundled", None, definition),
        )

        with pytest.raises(sqlite3.IntegrityError):
            temp_db.execute(
                """INSERT INTO rules (id, name, tier, project_id, definition, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                (rule_id_2, "no_push", "bundled", None, definition),
            )


# =============================================================================
# save_rule
# =============================================================================


class TestSaveRule:
    def test_save_bundled_rule(self, rule_store: RuleStore) -> None:
        rule = rule_store.save_rule(
            name="require_task",
            tier="bundled",
            definition={
                "tools": ["Edit", "Write"],
                "reason": "Claim a task first",
                "action": "block",
            },
        )
        assert rule["name"] == "require_task"
        assert rule["tier"] == "bundled"
        assert rule["project_id"] is None
        assert rule["id"] is not None
        assert rule["created_at"] is not None

    def test_save_user_rule(self, rule_store: RuleStore) -> None:
        rule = rule_store.save_rule(
            name="no_push",
            tier="user",
            definition={
                "tools": ["Bash"],
                "command_pattern": r"git\s+push",
                "reason": "No pushing",
                "action": "block",
            },
        )
        assert rule["tier"] == "user"

    def test_save_project_rule(self, rule_store: RuleStore, project_id: str) -> None:
        rule = rule_store.save_rule(
            name="require_tests",
            tier="project",
            project_id=project_id,
            definition={"tools": ["Bash"], "reason": "Run tests first", "action": "block"},
        )
        assert rule["tier"] == "project"
        assert rule["project_id"] == project_id

    def test_save_with_source_file(self, rule_store: RuleStore) -> None:
        rule = rule_store.save_rule(
            name="from_file",
            tier="bundled",
            definition={"reason": "test", "action": "block"},
            source_file="/path/to/rules/safety.yaml",
        )
        assert rule["source_file"] == "/path/to/rules/safety.yaml"

    def test_save_upsert_existing(self, rule_store: RuleStore) -> None:
        """Saving a rule with the same name+tier+project_id should update it."""
        rule1 = rule_store.save_rule(
            name="my_rule",
            tier="bundled",
            definition={"reason": "old reason", "action": "block"},
        )
        rule2 = rule_store.save_rule(
            name="my_rule",
            tier="bundled",
            definition={"reason": "new reason", "action": "warn"},
        )
        # Same ID (upsert)
        assert rule2["id"] == rule1["id"]
        # Definition updated
        assert rule2["definition"]["reason"] == "new reason"
        assert rule2["definition"]["action"] == "warn"

    def test_save_same_name_different_tiers(self, rule_store: RuleStore, project_id: str) -> None:
        """Same rule name can exist in different tiers."""
        r_bundled = rule_store.save_rule(
            name="no_push",
            tier="bundled",
            definition={"reason": "bundled reason", "action": "block"},
        )
        r_user = rule_store.save_rule(
            name="no_push",
            tier="user",
            definition={"reason": "user reason", "action": "warn"},
        )
        r_project = rule_store.save_rule(
            name="no_push",
            tier="project",
            project_id=project_id,
            definition={"reason": "project reason", "action": "allow"},
        )
        # All three should have different IDs
        ids = {r_bundled["id"], r_user["id"], r_project["id"]}
        assert len(ids) == 3

    def test_save_invalid_tier(self, rule_store: RuleStore) -> None:
        with pytest.raises(ValueError, match="Invalid tier"):
            rule_store.save_rule(
                name="bad",
                tier="invalid",
                definition={"reason": "test", "action": "block"},
            )

    def test_save_project_tier_requires_project_id(self, rule_store: RuleStore) -> None:
        with pytest.raises(ValueError, match="project_id"):
            rule_store.save_rule(
                name="bad",
                tier="project",
                definition={"reason": "test", "action": "block"},
            )


# =============================================================================
# get_rule (with tier precedence)
# =============================================================================


class TestGetRule:
    def test_get_bundled_rule(self, rule_store: RuleStore) -> None:
        rule_store.save_rule(
            name="my_rule",
            tier="bundled",
            definition={"reason": "bundled", "action": "block"},
        )
        rule = rule_store.get_rule("my_rule")
        assert rule is not None
        assert rule["definition"]["reason"] == "bundled"

    def test_get_nonexistent(self, rule_store: RuleStore) -> None:
        assert rule_store.get_rule("nonexistent") is None

    def test_tier_precedence_user_over_bundled(self, rule_store: RuleStore) -> None:
        """User-tier rule should override bundled-tier rule."""
        rule_store.save_rule(
            name="rule_x",
            tier="bundled",
            definition={"reason": "bundled", "action": "block"},
        )
        rule_store.save_rule(
            name="rule_x",
            tier="user",
            definition={"reason": "user override", "action": "warn"},
        )
        rule = rule_store.get_rule("rule_x")
        assert rule is not None
        assert rule["tier"] == "user"
        assert rule["definition"]["reason"] == "user override"

    def test_tier_precedence_project_over_user(
        self, rule_store: RuleStore, project_id: str
    ) -> None:
        """Project-tier rule should override user-tier rule."""
        rule_store.save_rule(
            name="rule_y",
            tier="bundled",
            definition={"reason": "bundled", "action": "block"},
        )
        rule_store.save_rule(
            name="rule_y",
            tier="user",
            definition={"reason": "user", "action": "warn"},
        )
        rule_store.save_rule(
            name="rule_y",
            tier="project",
            project_id=project_id,
            definition={"reason": "project wins", "action": "allow"},
        )
        rule = rule_store.get_rule("rule_y", project_id=project_id)
        assert rule is not None
        assert rule["tier"] == "project"
        assert rule["definition"]["reason"] == "project wins"

    def test_get_without_project_id_skips_project_tier(
        self, rule_store: RuleStore, project_id: str
    ) -> None:
        """Without project_id, project-tier rules are not considered."""
        rule_store.save_rule(
            name="rule_z",
            tier="bundled",
            definition={"reason": "bundled", "action": "block"},
        )
        rule_store.save_rule(
            name="rule_z",
            tier="project",
            project_id=project_id,
            definition={"reason": "project", "action": "allow"},
        )
        # Without project_id, should get bundled
        rule = rule_store.get_rule("rule_z")
        assert rule is not None
        assert rule["tier"] == "bundled"

    def test_get_specific_tier(self, rule_store: RuleStore) -> None:
        """Can request a specific tier explicitly."""
        rule_store.save_rule(
            name="rule_a",
            tier="bundled",
            definition={"reason": "bundled", "action": "block"},
        )
        rule_store.save_rule(
            name="rule_a",
            tier="user",
            definition={"reason": "user", "action": "warn"},
        )
        # Explicitly request bundled tier
        rule = rule_store.get_rule("rule_a", tier="bundled")
        assert rule is not None
        assert rule["tier"] == "bundled"


# =============================================================================
# list_rules
# =============================================================================


class TestListRules:
    def test_list_empty(self, rule_store: RuleStore) -> None:
        assert rule_store.list_rules() == []

    def test_list_all(self, rule_store: RuleStore) -> None:
        rule_store.save_rule(
            name="r1", tier="bundled", definition={"reason": "a", "action": "block"}
        )
        rule_store.save_rule(name="r2", tier="user", definition={"reason": "b", "action": "warn"})
        rules = rule_store.list_rules()
        assert len(rules) == 2

    def test_list_by_tier(self, rule_store: RuleStore, project_id: str) -> None:
        rule_store.save_rule(
            name="r1", tier="bundled", definition={"reason": "a", "action": "block"}
        )
        rule_store.save_rule(name="r2", tier="user", definition={"reason": "b", "action": "warn"})
        rule_store.save_rule(
            name="r3",
            tier="project",
            project_id=project_id,
            definition={"reason": "c", "action": "allow"},
        )

        bundled = rule_store.list_rules(tier="bundled")
        assert len(bundled) == 1
        assert bundled[0]["name"] == "r1"

        user = rule_store.list_rules(tier="user")
        assert len(user) == 1
        assert user[0]["name"] == "r2"

        project = rule_store.list_rules(tier="project")
        assert len(project) == 1
        assert project[0]["name"] == "r3"

    def test_list_by_project_id(self, rule_store: RuleStore, project_id: str) -> None:
        pid2 = str(uuid.uuid4())
        rule_store.save_rule(
            name="r1",
            tier="project",
            project_id=project_id,
            definition={"reason": "a", "action": "block"},
        )

        # Create second project
        rule_store.db.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
            (pid2, f"project-{pid2[:8]}"),
        )
        rule_store.save_rule(
            name="r2",
            tier="project",
            project_id=pid2,
            definition={"reason": "b", "action": "block"},
        )

        rules = rule_store.list_rules(project_id=project_id)
        assert len(rules) == 1
        assert rules[0]["name"] == "r1"

    def test_list_sorted_by_name(self, rule_store: RuleStore) -> None:
        rule_store.save_rule(
            name="zebra", tier="bundled", definition={"reason": "z", "action": "block"}
        )
        rule_store.save_rule(
            name="alpha", tier="bundled", definition={"reason": "a", "action": "block"}
        )
        rules = rule_store.list_rules()
        assert rules[0]["name"] == "alpha"
        assert rules[1]["name"] == "zebra"


# =============================================================================
# get_rules_by_tier
# =============================================================================


class TestGetRulesByTier:
    def test_get_rules_by_tier(self, rule_store: RuleStore) -> None:
        rule_store.save_rule(
            name="r1", tier="bundled", definition={"reason": "a", "action": "block"}
        )
        rule_store.save_rule(
            name="r2", tier="bundled", definition={"reason": "b", "action": "warn"}
        )
        rule_store.save_rule(name="r3", tier="user", definition={"reason": "c", "action": "block"})

        bundled = rule_store.get_rules_by_tier("bundled")
        assert len(bundled) == 2
        names = {r["name"] for r in bundled}
        assert names == {"r1", "r2"}

    def test_get_rules_by_tier_empty(self, rule_store: RuleStore) -> None:
        assert rule_store.get_rules_by_tier("user") == []


# =============================================================================
# delete_rule
# =============================================================================


class TestDeleteRule:
    def test_delete_existing(self, rule_store: RuleStore) -> None:
        rule = rule_store.save_rule(
            name="doomed", tier="bundled", definition={"reason": "test", "action": "block"}
        )
        assert rule_store.delete_rule(rule["id"]) is True
        assert rule_store.get_rule("doomed") is None

    def test_delete_nonexistent(self, rule_store: RuleStore) -> None:
        assert rule_store.delete_rule(str(uuid.uuid4())) is False

    def test_delete_by_name_and_tier(self, rule_store: RuleStore) -> None:
        rule_store.save_rule(
            name="target", tier="bundled", definition={"reason": "test", "action": "block"}
        )
        rule_store.save_rule(
            name="target", tier="user", definition={"reason": "test", "action": "warn"}
        )

        assert rule_store.delete_rule_by_name("target", tier="bundled") is True
        # User tier should still exist
        rule = rule_store.get_rule("target")
        assert rule is not None
        assert rule["tier"] == "user"

    def test_delete_by_name_nonexistent(self, rule_store: RuleStore) -> None:
        assert rule_store.delete_rule_by_name("nonexistent", tier="bundled") is False


# =============================================================================
# get_rules_by_source_file
# =============================================================================


class TestGetRulesBySourceFile:
    """Tests for get_rules_by_source_file method."""

    def test_returns_matching_rules(self, rule_store: RuleStore) -> None:
        """Returns all rules from a given source file."""
        rule_store.save_rule(
            name="rule_a",
            tier="bundled",
            definition={"reason": "a", "action": "block"},
            source_file="/bundled/rules/safety.yaml",
        )
        rule_store.save_rule(
            name="rule_b",
            tier="bundled",
            definition={"reason": "b", "action": "warn"},
            source_file="/bundled/rules/safety.yaml",
        )
        rule_store.save_rule(
            name="rule_c",
            tier="bundled",
            definition={"reason": "c", "action": "block"},
            source_file="/bundled/rules/quality.yaml",
        )

        result = rule_store.get_rules_by_source_file("/bundled/rules/safety.yaml")
        assert len(result) == 2
        names = {r["name"] for r in result}
        assert names == {"rule_a", "rule_b"}

    def test_returns_empty_for_unknown_file(self, rule_store: RuleStore) -> None:
        """Returns empty list when no rules match the source file."""
        assert rule_store.get_rules_by_source_file("/nonexistent.yaml") == []

    def test_filters_by_tier(self, rule_store: RuleStore) -> None:
        """Tier filter restricts results to matching tier."""
        rule_store.save_rule(
            name="bundled_rule",
            tier="bundled",
            definition={"reason": "b", "action": "block"},
            source_file="/rules/shared.yaml",
        )
        rule_store.save_rule(
            name="user_rule",
            tier="user",
            definition={"reason": "u", "action": "warn"},
            source_file="/rules/shared.yaml",
        )

        bundled_only = rule_store.get_rules_by_source_file(
            "/rules/shared.yaml", tier="bundled"
        )
        assert len(bundled_only) == 1
        assert bundled_only[0]["name"] == "bundled_rule"

    def test_sorted_by_name(self, rule_store: RuleStore) -> None:
        """Results are sorted alphabetically by name."""
        rule_store.save_rule(
            name="z_rule",
            tier="bundled",
            definition={"reason": "z", "action": "block"},
            source_file="/rules/test.yaml",
        )
        rule_store.save_rule(
            name="a_rule",
            tier="bundled",
            definition={"reason": "a", "action": "block"},
            source_file="/rules/test.yaml",
        )

        result = rule_store.get_rules_by_source_file("/rules/test.yaml")
        assert [r["name"] for r in result] == ["a_rule", "z_rule"]
