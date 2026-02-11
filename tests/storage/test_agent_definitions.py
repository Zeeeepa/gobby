"""Tests for LocalAgentDefinitionManager."""

from pathlib import Path

import pytest

from gobby.storage.agent_definitions import AgentDefinitionRow, LocalAgentDefinitionManager
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations

pytestmark = pytest.mark.unit

PROJECT_ID = "test-project-id"


def _setup_db(tmp_path: Path) -> LocalDatabase:
    """Create a fresh database with migrations applied."""
    db = LocalDatabase(tmp_path / "test.db")
    run_migrations(db)
    # Create a project for FK references
    db.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        (PROJECT_ID, "test-project"),
    )
    return db


class TestAgentDefinitionRow:
    """Tests for AgentDefinitionRow dataclass."""

    def test_to_dict_roundtrip(self) -> None:
        row = AgentDefinitionRow(
            id="abc",
            name="test",
            provider="claude",
            mode="headless",
            terminal="auto",
            base_branch="main",
            timeout=60.0,
            max_turns=5,
            enabled=True,
            created_at="2025-01-01T00:00:00",
            updated_at="2025-01-01T00:00:00",
            description="A test agent",
            workflows={"box": {"file": "box.yaml"}},
        )
        d = row.to_dict()
        assert d["name"] == "test"
        assert d["provider"] == "claude"
        assert d["workflows"] == {"box": {"file": "box.yaml"}}
        assert d["description"] == "A test agent"


class TestBuildPromptPreamble:
    """Tests for AgentDefinition.build_prompt_preamble()."""

    def test_all_fields_set(self) -> None:
        from gobby.agents.definitions import AgentDefinition

        defn = AgentDefinition(
            name="test",
            role="Security engineer",
            goal="Find vulnerabilities",
            personality="Concise and direct",
            instructions="Check OWASP top 10",
        )
        result = defn.build_prompt_preamble()
        assert result is not None
        assert "## Role\nSecurity engineer" in result
        assert "## Goal\nFind vulnerabilities" in result
        assert "## Personality\nConcise and direct" in result
        assert "## Instructions\nCheck OWASP top 10" in result

    def test_partial_fields(self) -> None:
        from gobby.agents.definitions import AgentDefinition

        defn = AgentDefinition(name="test", role="Dev agent", instructions="Write tests")
        result = defn.build_prompt_preamble()
        assert result is not None
        assert "## Role\nDev agent" in result
        assert "## Instructions\nWrite tests" in result
        assert "## Goal" not in result
        assert "## Personality" not in result

    def test_no_fields_returns_none(self) -> None:
        from gobby.agents.definitions import AgentDefinition

        defn = AgentDefinition(name="test")
        assert defn.build_prompt_preamble() is None


class TestLocalAgentDefinitionManager:
    """Tests for CRUD operations."""

    def test_create_and_get(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        row = mgr.create(name="my-agent", provider="claude", mode="headless")
        assert row.name == "my-agent"
        assert row.provider == "claude"
        assert row.mode == "headless"
        assert row.enabled is True

        fetched = mgr.get(row.id)
        assert fetched.name == "my-agent"
        assert fetched.id == row.id

    def test_create_with_all_fields(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        row = mgr.create(
            name="full-agent",
            project_id=PROJECT_ID,
            description="Full config",
            provider="gemini",
            model="gemini-pro",
            mode="terminal",
            terminal="tmux",
            isolation="clone",
            base_branch="dev",
            timeout=300.0,
            max_turns=20,
            default_workflow="worker",
            sandbox_config={"enabled": True, "mode": "permissive"},
            skill_profile={"audience": "developer"},
            workflows={"worker": {"type": "step", "steps": [{"name": "work"}]}},
            lifecycle_variables={"require_task": True},
            default_variables={"verbose": True},
        )

        assert row.project_id == PROJECT_ID
        assert row.provider == "gemini"
        assert row.model == "gemini-pro"
        assert row.isolation == "clone"
        assert row.sandbox_config == {"enabled": True, "mode": "permissive"}
        assert row.workflows == {"worker": {"type": "step", "steps": [{"name": "work"}]}}
        assert row.lifecycle_variables == {"require_task": True}

    def test_get_not_found(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        with pytest.raises(ValueError, match="not found"):
            mgr.get("nonexistent-id")

    def test_get_by_name_project_scoped(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        mgr.create(name="agent-a", project_id=PROJECT_ID, provider="claude")
        mgr.create(name="agent-a", provider="gemini")  # global

        # Project-scoped lookup returns project version
        result = mgr.get_by_name("agent-a", PROJECT_ID)
        assert result is not None
        assert result.provider == "claude"
        assert result.project_id == PROJECT_ID

    def test_get_by_name_global_fallback(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        mgr.create(name="agent-b", provider="gemini")  # global only

        result = mgr.get_by_name("agent-b", PROJECT_ID)
        assert result is not None
        assert result.provider == "gemini"
        assert result.project_id is None

    def test_get_by_name_not_found(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        assert mgr.get_by_name("nonexistent") is None

    def test_update(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        row = mgr.create(name="update-me", provider="claude", mode="headless")
        updated = mgr.update(row.id, mode="terminal", timeout=60.0)

        assert updated.mode == "terminal"
        assert updated.timeout == 60.0
        assert updated.name == "update-me"  # unchanged

    def test_update_json_fields(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        row = mgr.create(name="json-test", provider="claude")
        updated = mgr.update(
            row.id,
            sandbox_config={"enabled": True},
            workflows={"w1": {"file": "w1.yaml"}},
        )

        assert updated.sandbox_config == {"enabled": True}
        assert updated.workflows == {"w1": {"file": "w1.yaml"}}

    def test_update_no_fields(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        row = mgr.create(name="noop", provider="claude")
        updated = mgr.update(row.id)
        assert updated.id == row.id

    def test_delete(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        row = mgr.create(name="delete-me", provider="claude")
        assert mgr.delete(row.id) is True

        with pytest.raises(ValueError, match="not found"):
            mgr.get(row.id)

    def test_delete_not_found(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)
        assert mgr.delete("nonexistent") is False

    def test_list_by_project(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        mgr.create(name="proj-a", project_id=PROJECT_ID, provider="claude")
        mgr.create(name="proj-b", project_id=PROJECT_ID, provider="gemini")
        mgr.create(name="global-c", provider="claude")  # no project

        results = mgr.list_by_project(PROJECT_ID)
        assert len(results) == 2
        names = {r.name for r in results}
        assert names == {"proj-a", "proj-b"}

    def test_list_global(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        mgr.create(name="global-1", provider="claude")
        mgr.create(name="global-2", provider="gemini")
        mgr.create(name="proj-1", project_id=PROJECT_ID, provider="claude")

        results = mgr.list_global()
        assert len(results) == 2
        names = {r.name for r in results}
        assert names == {"global-1", "global-2"}

    def test_list_all_with_project(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        mgr.create(name="proj-a", project_id=PROJECT_ID, provider="claude")
        mgr.create(name="global-b", provider="gemini")

        results = mgr.list_all(project_id=PROJECT_ID)
        assert len(results) == 2

    def test_list_all_no_project(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        mgr.create(name="a", provider="claude")
        mgr.create(name="b", project_id=PROJECT_ID, provider="gemini")

        results = mgr.list_all()
        assert len(results) == 2

    def test_import_from_definition(self, tmp_path: Path) -> None:
        from gobby.agents.definitions import AgentDefinition

        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        defn = AgentDefinition(
            name="imported",
            description="An imported agent",
            provider="claude",
            mode="terminal",
            terminal="tmux",
            timeout=180.0,
            max_turns=15,
        )

        row = mgr.import_from_definition(defn, project_id=PROJECT_ID)
        assert row.name == "imported"
        assert row.provider == "claude"
        assert row.mode == "terminal"
        assert row.project_id == PROJECT_ID

    def test_export_to_definition(self, tmp_path: Path) -> None:
        from gobby.agents.definitions import AgentDefinition

        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        row = mgr.create(
            name="exportable",
            description="Export test",
            provider="gemini",
            model="gemini-pro",
            mode="terminal",
            isolation="worktree",
        )

        defn = mgr.export_to_definition(row.id)
        assert isinstance(defn, AgentDefinition)
        assert defn.name == "exportable"
        assert defn.provider == "gemini"
        assert defn.model == "gemini-pro"
        assert defn.isolation == "worktree"

    def test_import_export_roundtrip(self, tmp_path: Path) -> None:
        from gobby.agents.definitions import AgentDefinition

        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        original = AgentDefinition(
            name="roundtrip",
            provider="claude",
            mode="headless",
            timeout=99.0,
            max_turns=7,
            base_branch="dev",
        )

        row = mgr.import_from_definition(original)
        exported = mgr.export_to_definition(row.id)

        assert exported.name == original.name
        assert exported.provider == original.provider
        assert exported.mode == original.mode
        assert exported.timeout == original.timeout
        assert exported.max_turns == original.max_turns
        assert exported.base_branch == original.base_branch

    def test_unique_constraint_project_name(self, tmp_path: Path) -> None:
        """Duplicate name within same project should fail."""
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        mgr.create(name="dup", project_id=PROJECT_ID)
        with pytest.raises(Exception):
            mgr.create(name="dup", project_id=PROJECT_ID)

    def test_unique_constraint_global_name(self, tmp_path: Path) -> None:
        """Duplicate global name should fail."""
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        mgr.create(name="dup-global")
        with pytest.raises(Exception):
            mgr.create(name="dup-global")

    def test_create_with_prompt_fields(self, tmp_path: Path) -> None:
        """Verify role/goal/personality/instructions are stored and retrieved."""
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        row = mgr.create(
            name="persona-agent",
            role="Senior security engineer",
            goal="Every PR reviewed for OWASP top 10 vulnerabilities",
            personality="Ultra-succinct. Speaks in file paths.",
            instructions="Review all changed files. Check for bugs.",
        )

        assert row.role == "Senior security engineer"
        assert row.goal == "Every PR reviewed for OWASP top 10 vulnerabilities"
        assert row.personality == "Ultra-succinct. Speaks in file paths."
        assert row.instructions == "Review all changed files. Check for bugs."

        # Verify persistence via fresh fetch
        fetched = mgr.get(row.id)
        assert fetched.role == row.role
        assert fetched.goal == row.goal
        assert fetched.personality == row.personality
        assert fetched.instructions == row.instructions

        # Verify to_dict includes fields
        d = fetched.to_dict()
        assert d["role"] == "Senior security engineer"
        assert d["goal"] == "Every PR reviewed for OWASP top 10 vulnerabilities"
        assert d["personality"] == "Ultra-succinct. Speaks in file paths."
        assert d["instructions"] == "Review all changed files. Check for bugs."

    def test_import_export_roundtrip_with_prompt_fields(self, tmp_path: Path) -> None:
        """Verify role/goal/personality/instructions survive import/export roundtrip."""
        from gobby.agents.definitions import AgentDefinition

        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        original = AgentDefinition(
            name="roundtrip-prompts",
            provider="claude",
            mode="headless",
            role="QA specialist",
            goal="Ship quality, not perfection",
            personality="Thorough but pragmatic",
            instructions="Fix issues in-place. Run tests after fixes.",
        )

        row = mgr.import_from_definition(original)
        exported = mgr.export_to_definition(row.id)

        assert exported.role == original.role
        assert exported.goal == original.goal
        assert exported.personality == original.personality
        assert exported.instructions == original.instructions

    def test_same_name_different_scopes(self, tmp_path: Path) -> None:
        """Same name in project vs global should be allowed."""
        db = _setup_db(tmp_path)
        mgr = LocalAgentDefinitionManager(db)

        r1 = mgr.create(name="shared", project_id=PROJECT_ID, provider="claude")
        r2 = mgr.create(name="shared", provider="gemini")  # global

        assert r1.id != r2.id
        assert r1.project_id == PROJECT_ID
        assert r2.project_id is None
