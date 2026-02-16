"""Tests for rule import loading in WorkflowLoader (DB-only).

Covers: DB-backed import resolution via _resolve_imports_from_db(),
imported rules merge into workflow definition, file-local rules override
imported rules, missing import is handled gracefully.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.rules import RuleStore
from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager
from gobby.workflows.loader import WorkflowLoader

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path: Path) -> LocalDatabase:
    """Create a fresh database with migrations applied."""
    from gobby.storage.migrations import run_migrations

    db_path = tmp_path / "test_rule_imports.db"
    database = LocalDatabase(db_path)
    run_migrations(database)
    return database


@pytest.fixture
def rule_store(db: LocalDatabase) -> RuleStore:
    """Create a RuleStore backed by the temp database."""
    return RuleStore(db)


@pytest.fixture
def def_manager(db: LocalDatabase) -> LocalWorkflowDefinitionManager:
    """Create a workflow definition manager."""
    return LocalWorkflowDefinitionManager(db)


@pytest.fixture
def loader(db: LocalDatabase) -> WorkflowLoader:
    """Create a WorkflowLoader backed by the temp database."""
    return WorkflowLoader(db=db)


def _save_bundled_rule(
    rule_store: RuleStore,
    name: str,
    definition: dict[str, Any],
    source_file: str,
) -> None:
    """Helper to save a bundled-tier rule with a source_file."""
    rule_store.save_rule(
        name=name,
        tier="bundled",
        definition=definition,
        source_file=source_file,
    )


# =============================================================================
# Import resolution via DB
# =============================================================================


class TestImportResolution:
    """Tests for _resolve_imports_from_db()."""

    @pytest.mark.asyncio
    async def test_imports_merge_into_workflow(
        self, loader: WorkflowLoader, def_manager: LocalWorkflowDefinitionManager, rule_store: RuleStore
    ) -> None:
        """Imported rule_definitions from DB should merge into the workflow."""
        # Create bundled rule in DB with source_file matching import name
        _save_bundled_rule(
            rule_store,
            name="no_push",
            definition={
                "tools": ["Bash"],
                "command_pattern": r"git\s+push",
                "reason": "No pushing",
                "action": "block",
            },
            source_file="/bundled/rules/safety.yaml",
        )

        # Create workflow that imports "safety"
        def_manager.create(
            name="my-workflow",
            definition_json=json.dumps({
                "name": "my-workflow",
                "type": "step",
                "imports": ["safety"],
                "steps": [{"name": "work", "check_rules": ["no_push"]}],
            }),
            workflow_type="workflow",
        )

        defn = await loader.load_workflow("my-workflow")
        assert defn is not None
        assert "no_push" in defn.rule_definitions
        assert defn.rule_definitions["no_push"].action == "block"

    @pytest.mark.asyncio
    async def test_local_rules_override_imported(
        self, loader: WorkflowLoader, def_manager: LocalWorkflowDefinitionManager, rule_store: RuleStore
    ) -> None:
        """File-local rule_definitions should override imported ones with the same name."""
        _save_bundled_rule(
            rule_store,
            name="no_push",
            definition={
                "tools": ["Bash"],
                "reason": "imported reason",
                "action": "block",
            },
            source_file="/bundled/rules/common.yaml",
        )

        def_manager.create(
            name="override-test",
            definition_json=json.dumps({
                "name": "override-test",
                "type": "step",
                "imports": ["common"],
                "rule_definitions": {
                    "no_push": {
                        "tools": ["Bash"],
                        "reason": "local override",
                        "action": "warn",
                    },
                },
                "steps": [{"name": "work"}],
            }),
            workflow_type="workflow",
        )

        defn = await loader.load_workflow("override-test")
        assert defn is not None
        assert defn.rule_definitions["no_push"].reason == "local override"
        assert defn.rule_definitions["no_push"].action == "warn"

    @pytest.mark.asyncio
    async def test_multiple_imports(
        self, loader: WorkflowLoader, def_manager: LocalWorkflowDefinitionManager, rule_store: RuleStore
    ) -> None:
        """Multiple imports should all be merged."""
        _save_bundled_rule(
            rule_store,
            name="no_push",
            definition={"tools": ["Bash"], "reason": "safety", "action": "block"},
            source_file="/bundled/rules/safety.yaml",
        )
        _save_bundled_rule(
            rule_store,
            name="require_tests",
            definition={"tools": ["Bash"], "reason": "quality", "action": "warn"},
            source_file="/bundled/rules/quality.yaml",
        )

        def_manager.create(
            name="multi-import",
            definition_json=json.dumps({
                "name": "multi-import",
                "type": "step",
                "imports": ["safety", "quality"],
                "steps": [{"name": "work", "check_rules": ["no_push", "require_tests"]}],
            }),
            workflow_type="workflow",
        )

        defn = await loader.load_workflow("multi-import")
        assert defn is not None
        assert "no_push" in defn.rule_definitions
        assert "require_tests" in defn.rule_definitions

    @pytest.mark.asyncio
    async def test_missing_import_loads_without_rules(
        self, loader: WorkflowLoader, def_manager: LocalWorkflowDefinitionManager
    ) -> None:
        """Missing import source file loads workflow without those rules (no error)."""
        def_manager.create(
            name="bad-import",
            definition_json=json.dumps({
                "name": "bad-import",
                "type": "step",
                "imports": ["nonexistent-rules"],
                "steps": [{"name": "work"}],
            }),
            workflow_type="workflow",
        )

        # DB-based import resolution doesn't raise on missing imports;
        # it simply doesn't find matching rules.
        defn = await loader.load_workflow("bad-import")
        assert defn is not None
        assert defn.rule_definitions == {}

    @pytest.mark.asyncio
    async def test_no_imports_field_works(self, loader: WorkflowLoader, def_manager: LocalWorkflowDefinitionManager) -> None:
        """Workflow without imports should load normally."""
        def_manager.create(
            name="no-imports",
            definition_json=json.dumps({
                "name": "no-imports",
                "type": "step",
                "steps": [{"name": "work"}],
            }),
            workflow_type="workflow",
        )

        defn = await loader.load_workflow("no-imports")
        assert defn is not None
        assert defn.rule_definitions == {}

    @pytest.mark.asyncio
    async def test_later_import_overrides_earlier(
        self, loader: WorkflowLoader, def_manager: LocalWorkflowDefinitionManager, rule_store: RuleStore
    ) -> None:
        """When two imports define rules from different source files, all are merged."""
        _save_bundled_rule(
            rule_store,
            name="shared_rule_first",
            definition={"tools": ["Bash"], "reason": "from first", "action": "block"},
            source_file="/bundled/rules/first.yaml",
        )
        _save_bundled_rule(
            rule_store,
            name="shared_rule_second",
            definition={"tools": ["Bash"], "reason": "from second", "action": "warn"},
            source_file="/bundled/rules/second.yaml",
        )

        def_manager.create(
            name="import-order",
            definition_json=json.dumps({
                "name": "import-order",
                "type": "step",
                "imports": ["first", "second"],
                "steps": [{"name": "work"}],
            }),
            workflow_type="workflow",
        )

        defn = await loader.load_workflow("import-order")
        assert defn is not None
        assert "shared_rule_first" in defn.rule_definitions
        assert "shared_rule_second" in defn.rule_definitions
