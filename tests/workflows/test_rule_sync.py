"""Tests for bundled rule sync on daemon start.

Covers: sync loads rules from directory, sync upserts existing rules,
sync removes stale rules, sync handles empty directory, sync handles
malformed YAML gracefully.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gobby.storage.database import LocalDatabase

pytestmark = pytest.mark.unit


@pytest.fixture
def rules_dir(tmp_path: Path) -> Path:
    """Create a temporary rules directory with sample files."""
    d = tmp_path / "rules"
    d.mkdir()
    return d


def _write_rule_file(directory: Path, name: str, definitions: dict) -> Path:
    """Write a rule definitions YAML file."""
    path = directory / f"{name}.yaml"
    path.write_text(yaml.dump({"rule_definitions": definitions}, default_flow_style=False))
    return path


# =============================================================================
# sync_bundled_rules
# =============================================================================


class TestSyncBundledRules:
    def test_sync_loads_rules(self, temp_db: LocalDatabase, rules_dir: Path) -> None:
        """Sync should load all rule files and insert them into the DB."""
        from gobby.workflows.rule_sync import sync_bundled_rules_sync as sync_bundled_rules

        _write_rule_file(rules_dir, "safety", {
            "no_push": {
                "tools": ["Bash"],
                "command_pattern": r"git\s+push",
                "reason": "No pushing allowed",
                "action": "block",
            },
            "require_task": {
                "tools": ["Edit", "Write"],
                "reason": "Claim a task first",
                "action": "block",
            },
        })

        result = sync_bundled_rules(temp_db, rules_dir=rules_dir)
        assert result["success"] is True
        assert result["synced"] == 2
        assert result["errors"] == []

        # Verify rules are in the DB
        from gobby.storage.rules import RuleStore

        store = RuleStore(temp_db)
        rules = store.list_rules(tier="bundled")
        assert len(rules) == 2
        names = {r["name"] for r in rules}
        assert names == {"no_push", "require_task"}

    def test_sync_upserts_existing(self, temp_db: LocalDatabase, rules_dir: Path) -> None:
        """Syncing again should update existing rules, not duplicate them."""
        from gobby.workflows.rule_sync import sync_bundled_rules_sync as sync_bundled_rules

        _write_rule_file(rules_dir, "safety", {
            "no_push": {"tools": ["Bash"], "reason": "old reason", "action": "block"},
        })

        result1 = sync_bundled_rules(temp_db, rules_dir=rules_dir)
        assert result1["synced"] == 1

        # Update the file
        _write_rule_file(rules_dir, "safety", {
            "no_push": {"tools": ["Bash"], "reason": "new reason", "action": "warn"},
        })

        result2 = sync_bundled_rules(temp_db, rules_dir=rules_dir)
        assert result2["updated"] == 1
        assert result2["synced"] == 0

        # Verify updated
        from gobby.storage.rules import RuleStore

        store = RuleStore(temp_db)
        rule = store.get_rule("no_push")
        assert rule is not None
        assert rule["definition"]["reason"] == "new reason"
        assert rule["definition"]["action"] == "warn"

    def test_sync_removes_stale_rules(self, temp_db: LocalDatabase, rules_dir: Path) -> None:
        """Rules whose source files no longer exist should be removed."""
        from gobby.workflows.rule_sync import sync_bundled_rules_sync as sync_bundled_rules

        _write_rule_file(rules_dir, "safety", {
            "no_push": {"tools": ["Bash"], "reason": "test", "action": "block"},
        })

        result1 = sync_bundled_rules(temp_db, rules_dir=rules_dir)
        assert result1["synced"] == 1

        # Delete the file
        (rules_dir / "safety.yaml").unlink()

        result2 = sync_bundled_rules(temp_db, rules_dir=rules_dir)
        assert result2["removed"] == 1

        # Verify removed
        from gobby.storage.rules import RuleStore

        store = RuleStore(temp_db)
        assert store.get_rule("no_push") is None

    def test_sync_empty_directory(self, temp_db: LocalDatabase, rules_dir: Path) -> None:
        """Empty rules directory should succeed with zero counts."""
        from gobby.workflows.rule_sync import sync_bundled_rules_sync as sync_bundled_rules

        result = sync_bundled_rules(temp_db, rules_dir=rules_dir)
        assert result["success"] is True
        assert result["synced"] == 0

    def test_sync_missing_directory(self, temp_db: LocalDatabase, tmp_path: Path) -> None:
        """Nonexistent directory should succeed gracefully."""
        from gobby.workflows.rule_sync import sync_bundled_rules_sync as sync_bundled_rules

        result = sync_bundled_rules(temp_db, rules_dir=tmp_path / "nonexistent")
        assert result["success"] is True
        assert result["synced"] == 0

    def test_sync_malformed_yaml(self, temp_db: LocalDatabase, rules_dir: Path) -> None:
        """Malformed YAML should be skipped with error, not crash the sync."""
        from gobby.workflows.rule_sync import sync_bundled_rules_sync as sync_bundled_rules

        # Write a valid file
        _write_rule_file(rules_dir, "good", {
            "valid_rule": {"tools": ["Bash"], "reason": "test", "action": "block"},
        })

        # Write a malformed file
        (rules_dir / "bad.yaml").write_text("rule_definitions:\n  bad_rule:\n    - invalid list not dict")

        result = sync_bundled_rules(temp_db, rules_dir=rules_dir)
        assert result["synced"] == 1  # good file synced
        assert len(result["errors"]) >= 1  # bad file logged

    def test_sync_multiple_files(self, temp_db: LocalDatabase, rules_dir: Path) -> None:
        """Multiple rule files should all be synced."""
        from gobby.workflows.rule_sync import sync_bundled_rules_sync as sync_bundled_rules

        _write_rule_file(rules_dir, "safety", {
            "no_push": {"tools": ["Bash"], "reason": "safety", "action": "block"},
        })
        _write_rule_file(rules_dir, "quality", {
            "require_tests": {"tools": ["Bash"], "reason": "quality", "action": "warn"},
        })

        result = sync_bundled_rules(temp_db, rules_dir=rules_dir)
        assert result["synced"] == 2

        from gobby.storage.rules import RuleStore

        store = RuleStore(temp_db)
        rules = store.list_rules(tier="bundled")
        assert len(rules) == 2

    def test_sync_records_source_file(self, temp_db: LocalDatabase, rules_dir: Path) -> None:
        """Synced rules should record the source file path."""
        from gobby.workflows.rule_sync import sync_bundled_rules_sync as sync_bundled_rules

        _write_rule_file(rules_dir, "safety", {
            "no_push": {"tools": ["Bash"], "reason": "test", "action": "block"},
        })

        sync_bundled_rules(temp_db, rules_dir=rules_dir)

        from gobby.storage.rules import RuleStore

        store = RuleStore(temp_db)
        rule = store.get_rule("no_push")
        assert rule is not None
        assert rule["source_file"] is not None
        assert "safety.yaml" in rule["source_file"]

    def test_sync_skips_unchanged(self, temp_db: LocalDatabase, rules_dir: Path) -> None:
        """Syncing identical content should report skipped, not updated."""
        from gobby.workflows.rule_sync import sync_bundled_rules_sync as sync_bundled_rules

        _write_rule_file(rules_dir, "safety", {
            "no_push": {"tools": ["Bash"], "reason": "test", "action": "block"},
        })

        result1 = sync_bundled_rules(temp_db, rules_dir=rules_dir)
        assert result1["synced"] == 1

        result2 = sync_bundled_rules(temp_db, rules_dir=rules_dir)
        assert result2["synced"] == 0
        assert result2["updated"] == 0
        assert result2["skipped"] == 1
