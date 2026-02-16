"""
Tests for Named Agent Definitions.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.definitions import AgentDefinition, AgentDefinitionLoader, WorkflowSpec
from gobby.agents.sandbox import SandboxConfig

pytestmark = pytest.mark.unit


class TestAgentDefinition:
    """Tests for AgentDefinition Pydantic model."""

    def test_basic_validation(self) -> None:
        """Test basic schema validation."""
        data: dict[str, Any] = {
            "name": "test-agent",
            "description": "A test agent",
            "model": "haiku",
            "mode": "headless",
        }
        agent = AgentDefinition(**data)
        assert agent.name == "test-agent"
        assert agent.model == "haiku"
        assert agent.mode == "headless"
        assert agent.lifecycle_variables == {}  # Default empty dict
        assert agent.workflows is None

    def test_lifecycle_variables(self) -> None:
        """Test lifecycle variables validation."""
        data: dict[str, Any] = {
            "name": "test-agent",
            "description": "test",
            "lifecycle_variables": {
                "validation_model": None,
                "require_task": False,
                "some_int": 123,
            },
        }
        agent = AgentDefinition(**data)
        assert agent.lifecycle_variables["validation_model"] is None
        assert agent.lifecycle_variables["require_task"] is False
        assert agent.lifecycle_variables["some_int"] == 123

    def test_validation_errors(self) -> None:
        """Test validation fails for missing required fields."""
        # Missing name
        with pytest.raises(ValueError):
            AgentDefinition(name=None, description="test")  # type: ignore

    def test_isolation_fields_defaults(self) -> None:
        """Test that new isolation fields have correct defaults."""
        data: dict[str, Any] = {
            "name": "test-agent",
            "description": "A test agent",
        }
        agent = AgentDefinition(**data)

        # New fields with their expected defaults
        assert agent.isolation is None
        assert agent.branch_prefix is None
        assert agent.base_branch == "main"
        assert agent.provider == "claude"

    def test_isolation_fields_custom_values(self) -> None:
        """Test that new isolation fields accept custom values."""
        data: dict[str, Any] = {
            "name": "feature-developer",
            "description": "Agent for feature development",
            "isolation": "worktree",
            "branch_prefix": "feat/",
            "base_branch": "develop",
            "provider": "gemini",
        }
        agent = AgentDefinition(**data)

        assert agent.isolation == "worktree"
        assert agent.branch_prefix == "feat/"
        assert agent.base_branch == "develop"
        assert agent.provider == "gemini"

    def test_isolation_literal_values(self) -> None:
        """Test that isolation accepts all valid literal values."""
        for isolation_value in ["current", "worktree", "clone"]:
            data: dict[str, Any] = {
                "name": "test-agent",
                "isolation": isolation_value,
            }
            agent = AgentDefinition(**data)
            assert agent.isolation == isolation_value

    def test_yaml_loading_with_isolation_fields(self) -> None:
        """Test that YAML loading works with new isolation fields via load_from_file."""
        yaml_data: dict[str, Any] = {
            "name": "isolation-test-agent",
            "description": "Test agent with isolation config",
            "isolation": "clone",
            "branch_prefix": "agent/",
            "base_branch": "main",
            "provider": "claude",
        }

        with (
            patch("builtins.open"),
            patch("yaml.safe_load", return_value=yaml_data),
            patch("gobby.agents.definitions.Path") as mock_path_cls,
        ):
            # Make the shared path exist with our file
            mock_shared = MagicMock()
            mock_shared.exists.return_value = True
            mock_file = MagicMock()
            mock_file.exists.return_value = True
            mock_shared.__truediv__ = MagicMock(return_value=mock_file)
            mock_path_cls.return_value = mock_shared
            mock_path_cls.__truediv__ = MagicMock(return_value=mock_shared)

            agent = AgentDefinition(**yaml_data)

            assert agent is not None
            assert agent.name == "isolation-test-agent"
            assert agent.isolation == "clone"
            assert agent.branch_prefix == "agent/"
            assert agent.base_branch == "main"
            assert agent.provider == "claude"

    def test_sandbox_field_defaults_to_none(self) -> None:
        """Test that sandbox field defaults to None."""
        data: dict[str, Any] = {
            "name": "test-agent",
            "description": "A test agent",
        }
        agent = AgentDefinition(**data)

        assert agent.sandbox is None

    def test_sandbox_field_accepts_sandbox_config(self) -> None:
        """Test that sandbox field accepts SandboxConfig."""
        sandbox = SandboxConfig(
            enabled=True,
            mode="restrictive",
            allow_network=False,
            extra_read_paths=["/opt"],
            extra_write_paths=["/tmp"],
        )
        data: dict[str, Any] = {
            "name": "sandboxed-agent",
            "description": "Agent with sandbox config",
            "sandbox": sandbox,
        }
        agent = AgentDefinition(**data)

        assert agent.sandbox is not None
        assert agent.sandbox.enabled is True
        assert agent.sandbox.mode == "restrictive"
        assert agent.sandbox.allow_network is False
        assert agent.sandbox.extra_read_paths == ["/opt"]
        assert agent.sandbox.extra_write_paths == ["/tmp"]

    def test_yaml_loading_with_sandbox_config(self) -> None:
        """Test that sandbox config parses correctly from dict data."""
        yaml_data: dict[str, Any] = {
            "name": "sandboxed-agent",
            "description": "Agent with sandbox from YAML",
            "sandbox": {
                "enabled": True,
                "mode": "permissive",
                "allow_network": True,
                "extra_read_paths": ["/data"],
                "extra_write_paths": [],
            },
        }

        agent = AgentDefinition(**yaml_data)

        assert agent is not None
        assert agent.name == "sandboxed-agent"
        assert agent.sandbox is not None
        assert agent.sandbox.enabled is True
        assert agent.sandbox.mode == "permissive"
        assert agent.sandbox.extra_read_paths == ["/data"]


class TestAgentDefinitionLoader:
    """Tests for AgentDefinitionLoader (DB-first pattern)."""

    def test_load_from_db(self, tmp_path: Path) -> None:
        """Test loading a definition from the database."""
        from gobby.storage.agent_definitions import LocalAgentDefinitionManager
        from gobby.storage.database import LocalDatabase
        from gobby.storage.migrations import run_migrations

        db = LocalDatabase(tmp_path / "test.db")
        run_migrations(db)

        mgr = LocalAgentDefinitionManager(db, dev_mode=True)
        mgr.create(
            name="validation-runner",
            description="Runs validation",
            model="haiku",
            scope="bundled",
        )

        loader = AgentDefinitionLoader(db=db)
        agent = loader.load("validation-runner")

        assert agent is not None
        assert agent.name == "validation-runner"
        assert agent.model == "haiku"

    def test_load_definition_not_found(self, tmp_path: Path) -> None:
        """Test loading a definition that doesn't exist."""
        from gobby.storage.database import LocalDatabase
        from gobby.storage.migrations import run_migrations

        db = LocalDatabase(tmp_path / "test.db")
        run_migrations(db)

        loader = AgentDefinitionLoader(db=db)
        agent = loader.load("non-existent")
        assert agent is None

    def test_scope_precedence(self, tmp_path: Path) -> None:
        """Test scope precedence: project > global > bundled."""
        from gobby.storage.agent_definitions import LocalAgentDefinitionManager
        from gobby.storage.database import LocalDatabase
        from gobby.storage.migrations import run_migrations

        db = LocalDatabase(tmp_path / "test.db")
        run_migrations(db)
        db.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES ('proj-1', 'test', datetime('now'), datetime('now'))"
        )

        mgr = LocalAgentDefinitionManager(db, dev_mode=True)
        mgr.create(name="agent-x", provider="claude", scope="bundled")
        mgr.create(name="agent-x", provider="gemini", scope="global")
        mgr.create(name="agent-x", provider="codex", project_id="proj-1", scope="project")

        loader = AgentDefinitionLoader(db=db)

        # With project_id, project scope wins
        agent = loader.load("agent-x", project_id="proj-1")
        assert agent is not None
        assert agent.provider == "codex"

        # Without project_id, global wins over bundled
        agent = loader.load("agent-x")
        assert agent is not None
        assert agent.provider == "gemini"

    def test_load_from_file_static(self, tmp_path: Path) -> None:
        """Test static load_from_file method finds YAML files."""
        import yaml

        yaml_data: dict[str, Any] = {
            "name": "my-agent",
            "description": "Test agent",
            "provider": "claude",
        }

        # Create a real temp YAML file
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        yaml_file = agents_dir / "my-agent.yaml"
        yaml_file.write_text(yaml.dump(yaml_data))

        # Patch the shared path to point to our temp agents dir
        with (
            patch("gobby.agents.definitions.get_project_context", return_value=None),
            patch("gobby.agents.definitions.Path") as mock_path_cls,
        ):
            # Path(__file__).parent.parent => base_dir
            mock_base = MagicMock()
            mock_install_shared = MagicMock()
            mock_install_shared.exists.return_value = False
            mock_install = MagicMock()
            mock_install.__truediv__ = MagicMock(return_value=mock_install_shared)
            mock_base.__truediv__ = MagicMock(return_value=mock_install)
            mock_parent = MagicMock()
            mock_parent.parent = mock_base
            mock_file_path = MagicMock()
            mock_file_path.parent = mock_parent
            mock_path_cls.return_value = mock_file_path

            # Path.home() / ".gobby" / "agents" => our temp agents dir
            mock_home = MagicMock()
            mock_gobby_dir = MagicMock()
            mock_gobby_dir.__truediv__ = MagicMock(return_value=agents_dir)
            mock_home.__truediv__ = MagicMock(return_value=mock_gobby_dir)
            mock_path_cls.home.return_value = mock_home

            agent = AgentDefinitionLoader.load_from_file("my-agent")
            assert agent is not None
            assert agent.name == "my-agent"
            assert agent.provider == "claude"

    def test_list_all_from_db(self, tmp_path: Path) -> None:
        """Test list_all returns all definitions from DB."""
        from gobby.storage.agent_definitions import LocalAgentDefinitionManager
        from gobby.storage.database import LocalDatabase
        from gobby.storage.migrations import run_migrations

        db = LocalDatabase(tmp_path / "test.db")
        run_migrations(db)

        mgr = LocalAgentDefinitionManager(db, dev_mode=True)
        mgr.create(name="agent-a", provider="claude", scope="bundled")
        mgr.create(name="agent-b", provider="gemini", scope="global")

        loader = AgentDefinitionLoader(db=db)
        items = loader.list_all()
        assert len(items) == 2
        names = {i.definition.name for i in items}
        assert names == {"agent-a", "agent-b"}


class TestGetDbFallbackBehavior:
    """Tests for AgentDefinitionLoader._get_db warning and strict mode."""

    def test_get_db_warns_on_fallback(self, tmp_path: Path) -> None:
        """Test that _get_db emits a warning when falling back to LocalDatabase."""
        from unittest.mock import patch as mock_patch

        loader = AgentDefinitionLoader()  # No db injected

        with mock_patch(
            "gobby.storage.database.LocalDatabase"
        ) as mock_local_db_cls, mock_patch(
            "gobby.agents.definitions.logger"
        ) as mock_logger:
            mock_local_db_cls.return_value = MagicMock()
            db = loader._get_db()

            assert db is not None
            mock_logger.warning.assert_called_once()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "No database was injected" in warning_msg
            assert "db=" in warning_msg

    def test_get_db_warns_includes_default_path(self, tmp_path: Path) -> None:
        """Test that the fallback warning includes the default DB path."""
        from unittest.mock import patch as mock_patch

        loader = AgentDefinitionLoader()

        with mock_patch(
            "gobby.storage.database.LocalDatabase"
        ) as mock_local_db_cls, mock_patch(
            "gobby.agents.definitions.logger"
        ) as mock_logger:
            mock_local_db_cls.return_value = MagicMock()
            loader._get_db()

            # The path is passed as the second positional arg (for %s formatting)
            call_args = mock_logger.warning.call_args
            fmt_str = call_args[0][0]
            assert "%s" in fmt_str or "default path" in fmt_str.lower()

    def test_get_db_no_warning_when_injected(self, tmp_path: Path) -> None:
        """Test that _get_db does NOT warn when a db is injected."""
        from unittest.mock import patch as mock_patch

        mock_db = MagicMock()
        loader = AgentDefinitionLoader(db=mock_db)

        with mock_patch("gobby.agents.definitions.logger") as mock_logger:
            db = loader._get_db()

            assert db is mock_db
            mock_logger.warning.assert_not_called()

    def test_get_db_strict_flag_raises(self) -> None:
        """Test that strict=True raises RuntimeError when no db injected."""
        loader = AgentDefinitionLoader(strict=True)

        with pytest.raises(RuntimeError, match="requires an injected database"):
            loader._get_db()

    def test_get_db_strict_env_var_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that GOBBY_STRICT_DB_INJECTION=1 raises RuntimeError."""
        monkeypatch.setenv("GOBBY_STRICT_DB_INJECTION", "1")
        loader = AgentDefinitionLoader()

        with pytest.raises(RuntimeError, match="requires an injected database"):
            loader._get_db()

    def test_get_db_strict_flag_no_effect_when_db_injected(self) -> None:
        """Test that strict=True is fine when a db is actually injected."""
        mock_db = MagicMock()
        loader = AgentDefinitionLoader(db=mock_db, strict=True)

        db = loader._get_db()
        assert db is mock_db

    def test_get_db_strict_env_no_effect_when_db_injected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that GOBBY_STRICT_DB_INJECTION=1 is fine when db is injected."""
        monkeypatch.setenv("GOBBY_STRICT_DB_INJECTION", "1")
        mock_db = MagicMock()
        loader = AgentDefinitionLoader(db=mock_db)

        db = loader._get_db()
        assert db is mock_db

    def test_get_db_fallback_caches_instance(self) -> None:
        """Test that fallback LocalDatabase is cached on subsequent calls."""
        from unittest.mock import patch as mock_patch

        loader = AgentDefinitionLoader()

        with mock_patch(
            "gobby.storage.database.LocalDatabase"
        ) as mock_local_db_cls, mock_patch("gobby.agents.definitions.logger"):
            sentinel = MagicMock()
            mock_local_db_cls.return_value = sentinel

            db1 = loader._get_db()
            db2 = loader._get_db()

            assert db1 is db2 is sentinel
            # LocalDatabase constructor called only once
            mock_local_db_cls.assert_called_once()


class TestGenericAgentDefinition:
    """Tests for the generic agent definition model."""

    def test_generic_agent_loads_successfully(self) -> None:
        """Test that the generic agent definition model validates."""
        yaml_data: dict[str, Any] = {
            "name": "generic",
            "description": "Default generic agent",
            "mode": "terminal",
            "provider": "claude",
            "isolation": None,
            "base_branch": "main",
            "workflows": {"generic": {"file": "generic.yaml"}},
            "default_workflow": "generic",
            "timeout": 120.0,
            "max_turns": 10,
        }

        agent = AgentDefinition(**yaml_data)
        assert agent is not None
        assert agent.name == "generic"

    def test_generic_agent_has_expected_defaults(self) -> None:
        """Test that generic agent has correct default values."""
        yaml_data: dict[str, Any] = {
            "name": "generic",
            "description": "Default generic agent with minimal configuration.",
            "mode": "terminal",
            "provider": "claude",
            "base_branch": "main",
            "workflows": {"generic": {"file": "generic.yaml"}},
            "default_workflow": "generic",
            "timeout": 120.0,
            "max_turns": 10,
        }

        agent = AgentDefinition(**yaml_data)

        assert agent is not None
        assert agent.name == "generic"
        assert agent.mode == "terminal"
        assert agent.provider == "claude"
        assert agent.get_effective_workflow() == "generic"
        assert agent.timeout == 120.0
        assert agent.max_turns == 10
        assert agent.base_branch == "main"

    def test_generic_agent_isolation_is_null(self) -> None:
        """Test that generic agent has no isolation by default."""
        yaml_data: dict[str, Any] = {
            "name": "generic",
            "mode": "terminal",
            "provider": "claude",
            "workflows": {"generic": {"file": "generic.yaml"}},
            "default_workflow": "generic",
        }

        agent = AgentDefinition(**yaml_data)

        assert agent is not None
        assert agent.isolation is None


class TestSandboxedAgentDefinition:
    """Tests for the sandboxed.yaml agent definition."""

    def test_sandboxed_agent_loads_successfully(self) -> None:
        """Test that the sandboxed agent definition can be loaded."""
        loader = AgentDefinitionLoader()
        agent = loader.load("sandboxed")

        # Skip test if agent definition doesn't exist
        if agent is None:
            pytest.skip("sandboxed agent definition not installed")

        assert agent.name == "sandboxed"

    def test_sandboxed_agent_has_sandbox_enabled(self) -> None:
        """Test that sandboxed agent has sandbox.enabled=True."""
        loader = AgentDefinitionLoader()
        agent = loader.load("sandboxed")

        if agent is None:
            pytest.skip("sandboxed agent definition not installed")

        assert agent.sandbox is not None
        assert agent.sandbox.enabled is True

    def test_sandboxed_agent_has_permissive_mode(self) -> None:
        """Test that sandboxed agent uses permissive sandbox mode."""
        loader = AgentDefinitionLoader()
        agent = loader.load("sandboxed")

        if agent is None:
            pytest.skip("sandboxed agent definition not installed")

        assert agent.sandbox is not None
        assert agent.sandbox.mode == "permissive"

    def test_sandboxed_agent_allows_network(self) -> None:
        """Test that sandboxed agent allows network access."""
        loader = AgentDefinitionLoader()
        agent = loader.load("sandboxed")

        if agent is None:
            pytest.skip("sandboxed agent definition not installed")

        assert agent.sandbox is not None
        assert agent.sandbox.allow_network is True

    def test_sandboxed_agent_has_expected_mode(self) -> None:
        """Test that sandboxed agent uses headless mode."""
        loader = AgentDefinitionLoader()
        agent = loader.load("sandboxed")

        if agent is None:
            pytest.skip("sandboxed agent definition not installed")

        assert agent.mode == "headless"


class TestWorkflowSpec:
    """Tests for WorkflowSpec model."""

    def test_file_reference(self) -> None:
        """Test WorkflowSpec with file reference."""
        spec = WorkflowSpec(file="my-workflow.yaml")
        assert spec.is_file_reference() is True
        assert spec.is_inline() is False

    def test_inline_definition(self) -> None:
        """Test WorkflowSpec with inline definition."""
        spec = WorkflowSpec(
            type="step",
            steps=[{"name": "work", "description": "Do work"}],
            variables={"foo": "bar"},
        )
        assert spec.is_file_reference() is False
        assert spec.is_inline() is True

    def test_inline_with_type_only(self) -> None:
        """Test WorkflowSpec detects inline when type is set."""
        spec = WorkflowSpec(type="step")
        assert spec.is_inline() is True

    def test_empty_spec_is_neither(self) -> None:
        """Test empty WorkflowSpec is neither file nor inline."""
        spec = WorkflowSpec()
        assert spec.is_file_reference() is False
        assert spec.is_inline() is False


class TestAgentDefinitionWithWorkflows:
    """Tests for AgentDefinition with named workflows."""

    def test_workflows_map_basic(self) -> None:
        """Test AgentDefinition with workflows map."""
        data: dict[str, Any] = {
            "name": "multi-workflow-agent",
            "workflows": {
                "box": WorkflowSpec(file="box-workflow.yaml"),
                "worker": WorkflowSpec(type="step", steps=[]),
            },
            "default_workflow": "box",
        }
        agent = AgentDefinition(**data)

        assert agent.workflows is not None
        assert len(agent.workflows) == 2
        assert "box" in agent.workflows
        assert "worker" in agent.workflows
        assert agent.default_workflow == "box"

    def test_get_workflow_spec_by_name(self) -> None:
        """Test get_workflow_spec returns correct spec."""
        agent = AgentDefinition(
            name="test",
            workflows={
                "main": WorkflowSpec(file="main.yaml"),
                "alt": WorkflowSpec(type="step"),
            },
            default_workflow="main",
        )

        spec = agent.get_workflow_spec("main")
        assert spec is not None
        assert spec.file == "main.yaml"

        spec = agent.get_workflow_spec("alt")
        assert spec is not None
        assert spec.type == "step"

    def test_get_workflow_spec_default(self) -> None:
        """Test get_workflow_spec returns default when no name given."""
        agent = AgentDefinition(
            name="test",
            workflows={
                "main": WorkflowSpec(file="main.yaml"),
                "alt": WorkflowSpec(type="step"),
            },
            default_workflow="main",
        )

        spec = agent.get_workflow_spec()
        assert spec is not None
        assert spec.file == "main.yaml"

    def test_get_effective_workflow_file_reference(self) -> None:
        """Test get_effective_workflow for file reference."""
        agent = AgentDefinition(
            name="meeseeks",
            workflows={
                "box": WorkflowSpec(file="meeseeks-box.yaml"),
            },
            default_workflow="box",
        )

        # Should return filename without .yaml
        result = agent.get_effective_workflow("box")
        assert result == "meeseeks-box"

    def test_get_effective_workflow_inline(self) -> None:
        """Test get_effective_workflow for inline workflow."""
        agent = AgentDefinition(
            name="meeseeks",
            workflows={
                "worker": WorkflowSpec(type="step", steps=[]),
            },
            default_workflow="worker",
        )

        # Should return qualified name
        result = agent.get_effective_workflow("worker")
        assert result == "meeseeks:worker"

    def test_get_effective_workflow_default(self) -> None:
        """Test get_effective_workflow uses default when no param."""
        agent = AgentDefinition(
            name="meeseeks",
            workflows={
                "box": WorkflowSpec(file="meeseeks-box.yaml"),
            },
            default_workflow="box",
        )

        result = agent.get_effective_workflow()
        assert result == "meeseeks-box"

    def test_get_effective_workflow_external(self) -> None:
        """Test get_effective_workflow passes through external names."""
        agent = AgentDefinition(
            name="meeseeks",
            workflows={
                "box": WorkflowSpec(file="meeseeks-box.yaml"),
            },
            default_workflow="box",
        )

        # Workflow not in map - should return as-is
        result = agent.get_effective_workflow("some-external-workflow")
        assert result == "some-external-workflow"

    def test_get_effective_workflow_no_workflows_returns_none(self) -> None:
        """Test get_effective_workflow returns None when no workflows configured."""
        agent = AgentDefinition(
            name="bare-agent",
        )

        result = agent.get_effective_workflow()
        assert result is None

    def test_get_orchestrator_workflow_with_self_mode(self) -> None:
        """Test detection of orchestrator workflow with mode: self."""
        data: dict[str, Any] = {
            "name": "meeseeks",
            "default_workflow": "box",
            "workflows": {
                "box": {
                    "file": "meeseeks-box.yaml",
                    "mode": "self",  # Activates in caller session
                },
                "worker": {
                    "type": "step",
                    "steps": [],
                },
            },
        }
        agent = AgentDefinition(**data)

        # box workflow with mode: self is the orchestrator
        assert agent.get_orchestrator_workflow() == "box"

    def test_get_orchestrator_workflow_no_self_mode(self) -> None:
        """Test no orchestrator when default workflow doesn't have mode: self."""
        data: dict[str, Any] = {
            "name": "simple-agent",
            "default_workflow": "work",
            "workflows": {
                "work": {
                    "file": "work.yaml",
                    "mode": "terminal",  # Normal mode, not self
                },
            },
        }
        agent = AgentDefinition(**data)

        # No orchestrator - mode is not "self"
        assert agent.get_orchestrator_workflow() is None

    def test_get_orchestrator_workflow_no_default(self) -> None:
        """Test no orchestrator when no default workflow specified."""
        data: dict[str, Any] = {
            "name": "no-default-agent",
            "workflows": {
                "work": {
                    "file": "work.yaml",
                    "mode": "self",
                },
            },
        }
        agent = AgentDefinition(**data)

        # No orchestrator - no default_workflow set
        assert agent.get_orchestrator_workflow() is None

    def test_get_orchestrator_workflow_no_workflows(self) -> None:
        """Test no orchestrator when no workflows map."""
        data: dict[str, Any] = {
            "name": "basic-agent",
            "default_workflow": "work",
        }
        agent = AgentDefinition(**data)

        # No orchestrator - no workflows map
        assert agent.get_orchestrator_workflow() is None
