"""
Tests for workflow variable loading and merging.

Tests the following scenarios:
1. WorkflowDefinition.variables loaded from YAML
2. WorkflowState.variables initialized from definition defaults
3. Variable inheritance when workflows extend each other
4. Runtime variables override YAML defaults
5. Variable persistence through state_manager (save/load roundtrip)
6. Variable precedence pattern (explicit > workflow > config)
"""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.workflows.definitions import WorkflowDefinition, WorkflowState
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager

pytestmark = pytest.mark.unit


# =============================================================================
# aiofiles mock helpers
# =============================================================================


def mock_aiofiles_open(read_data: str = "") -> MagicMock:
    """Create a mock for aiofiles.open that returns read_data."""
    mock_file = AsyncMock()
    mock_file.read = AsyncMock(return_value=read_data)
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_file)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=mock_cm)


def mock_aiofiles_open_side_effect(content_fn: Callable[[str], Any]) -> Callable[..., Any]:
    """Create a side_effect function for aiofiles.open that dispatches by path."""

    def _open(path: str, *args: Any, **kwargs: Any) -> AsyncMock:
        content = content_fn(path)
        mock_file = AsyncMock()
        mock_file.read = AsyncMock(return_value=content)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_file)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        return mock_cm

    return _open


# =============================================================================
# Test WorkflowDefinition Variables Loading from YAML
# =============================================================================


class TestWorkflowDefinitionVariables:
    """Tests for loading variables from workflow YAML files."""

    @pytest.mark.asyncio
    async def test_load_workflow_with_variables(self) -> None:
        """Variables section from YAML is loaded into WorkflowDefinition."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])
        yaml_content = """
        name: test_workflow
        version: "1.0.0"
        type: lifecycle
        variables:
          require_task_before_edit: true
          tdd_mode: false
          session_task: null
        steps: []
        """

        with patch.object(
            loader,
            "_find_workflow_file",
            return_value=Path("/tmp/workflows/test_workflow.yaml"),
        ):
            with patch("aiofiles.open", mock_aiofiles_open(read_data=yaml_content)):
                wf = await loader.load_workflow("test_workflow")

        assert wf is not None
        assert wf.variables == {
            "require_task_before_edit": True,
            "tdd_mode": False,
            "session_task": None,
        }

    @pytest.mark.asyncio
    async def test_load_workflow_without_variables(self) -> None:
        """Workflow without variables section has empty dict."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])
        yaml_content = """
        name: no_vars_workflow
        version: "1.0.0"
        steps: []
        """

        with patch.object(
            loader,
            "_find_workflow_file",
            return_value=Path("/tmp/workflows/no_vars_workflow.yaml"),
        ):
            with patch("aiofiles.open", mock_aiofiles_open(read_data=yaml_content)):
                wf = await loader.load_workflow("no_vars_workflow")

        assert wf is not None
        assert wf.variables == {}

    @pytest.mark.asyncio
    async def test_variables_support_all_types(self) -> None:
        """Variables support string, int, float, bool, null, list, and dict values."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])
        yaml_content = """
        name: typed_vars
        version: "1.0.0"
        variables:
          string_var: "hello"
          int_var: 42
          float_var: 3.14
          bool_var: true
          null_var: null
          list_var: [1, 2, 3]
          dict_var:
            nested: value
        steps: []
        """

        with patch.object(
            loader,
            "_find_workflow_file",
            return_value=Path("/tmp/workflows/typed_vars.yaml"),
        ):
            with patch("aiofiles.open", mock_aiofiles_open(read_data=yaml_content)):
                wf = await loader.load_workflow("typed_vars")

        assert wf.variables["string_var"] == "hello"
        assert wf.variables["int_var"] == 42
        assert wf.variables["float_var"] == 3.14
        assert wf.variables["bool_var"] is True
        assert wf.variables["null_var"] is None
        assert wf.variables["list_var"] == [1, 2, 3]
        assert wf.variables["dict_var"] == {"nested": "value"}


class TestWorkflowVariableInheritance:
    """Tests for variable inheritance when workflows extend each other."""

    @pytest.mark.asyncio
    async def test_child_inherits_parent_variables(self) -> None:
        """Child workflow inherits variables from parent."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])

        parent_yaml = """
        name: parent
        version: "1.0.0"
        variables:
          from_parent: "inherited"
          shared: "parent_value"
        steps: []
        """

        child_yaml = """
        name: child
        version: "1.0.0"
        extends: parent
        variables:
          from_child: "new"
        steps: []
        """

        def mock_find(name, search_dirs):
            paths = {
                "parent": Path("/tmp/workflows/parent.yaml"),
                "child": Path("/tmp/workflows/child.yaml"),
            }
            return paths.get(name)

        def content_for_path(path):
            if "parent" in str(path):
                return parent_yaml
            if "child" in str(path):
                return child_yaml
            raise FileNotFoundError(path)

        with patch.object(loader, "_find_workflow_file", side_effect=mock_find):
            with patch(
                "aiofiles.open", side_effect=mock_aiofiles_open_side_effect(content_for_path)
            ):
                wf = await loader.load_workflow("child")

        assert wf is not None
        # Should have both parent and child variables
        assert wf.variables["from_parent"] == "inherited"
        assert wf.variables["from_child"] == "new"

    @pytest.mark.asyncio
    async def test_child_overrides_parent_variables(self) -> None:
        """Child variables override parent variables with same name."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])

        parent_yaml = """
        name: parent
        version: "1.0.0"
        variables:
          shared_var: "parent_value"
          only_parent: 100
        steps: []
        """

        child_yaml = """
        name: child
        version: "1.0.0"
        extends: parent
        variables:
          shared_var: "child_value"
        steps: []
        """

        def mock_find(name, search_dirs):
            paths = {
                "parent": Path("/tmp/workflows/parent.yaml"),
                "child": Path("/tmp/workflows/child.yaml"),
            }
            return paths.get(name)

        def content_for_path(path):
            if "parent" in str(path):
                return parent_yaml
            if "child" in str(path):
                return child_yaml
            raise FileNotFoundError(path)

        with patch.object(loader, "_find_workflow_file", side_effect=mock_find):
            with patch(
                "aiofiles.open", side_effect=mock_aiofiles_open_side_effect(content_for_path)
            ):
                wf = await loader.load_workflow("child")

        # Child overrides shared_var but inherits only_parent
        assert wf.variables["shared_var"] == "child_value"
        assert wf.variables["only_parent"] == 100

    @pytest.mark.asyncio
    async def test_three_level_inheritance_merges_variables(self) -> None:
        """Variables merge across three levels of inheritance."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])

        base_yaml = """
        name: base
        version: "1.0.0"
        variables:
          level: "base"
          from_base: true
        steps: []
        """

        middle_yaml = """
        name: middle
        version: "1.0.0"
        extends: base
        variables:
          level: "middle"
          from_middle: true
        steps: []
        """

        top_yaml = """
        name: top
        version: "1.0.0"
        extends: middle
        variables:
          level: "top"
          from_top: true
        steps: []
        """

        yamls = {"base": base_yaml, "middle": middle_yaml, "top": top_yaml}

        def mock_find(name, search_dirs):
            paths = {
                "base": Path("/tmp/workflows/base.yaml"),
                "middle": Path("/tmp/workflows/middle.yaml"),
                "top": Path("/tmp/workflows/top.yaml"),
            }
            return paths.get(name)

        def content_for_path(path):
            for name, content in yamls.items():
                if name in str(path):
                    return content
            raise FileNotFoundError(path)

        with patch.object(loader, "_find_workflow_file", side_effect=mock_find):
            with patch(
                "aiofiles.open", side_effect=mock_aiofiles_open_side_effect(content_for_path)
            ):
                wf = await loader.load_workflow("top")

        # Top overrides level, but inherits from all ancestors
        assert wf.variables["level"] == "top"
        assert wf.variables["from_base"] is True
        assert wf.variables["from_middle"] is True
        assert wf.variables["from_top"] is True


# =============================================================================
# Test WorkflowState Variables Persistence
# =============================================================================


class TestWorkflowStateVariablesPersistence:
    """Tests for variable persistence via WorkflowStateManager."""

    @pytest.fixture
    def state_manager(self, temp_db):
        """Create WorkflowStateManager with test database (uses temp_db from conftest)."""
        return WorkflowStateManager(temp_db)

    @pytest.fixture
    def session_id(self, temp_db):
        """Create a session for FK constraint and return its ID."""
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        # Create project first
        project_manager = LocalProjectManager(temp_db)
        project = project_manager.get_or_create("/tmp/test-project")

        # Create session using register method
        session_manager = LocalSessionManager(temp_db)
        session = session_manager.register(
            external_id="ext_001",
            machine_id="machine_001",
            source="claude_code",
            project_id=project.id,
        )
        return session.id

    def test_save_and_load_state_with_variables(self, state_manager, session_id) -> None:
        """Variables are persisted and loaded correctly."""

        # Create state with variables
        state = WorkflowState(
            session_id=session_id,
            workflow_name="test_workflow",
            step="step1",
            variables={
                "require_task_before_edit": True,
                "tdd_mode": False,
                "session_task": "gt-abc123",
                "count": 42,
            },
        )

        # Save
        state_manager.save_state(state)

        # Load
        loaded = state_manager.get_state(session_id)

        assert loaded is not None
        assert loaded.variables == {
            "require_task_before_edit": True,
            "tdd_mode": False,
            "session_task": "gt-abc123",
            "count": 42,
        }

    def test_update_state_preserves_variables(self, state_manager, session_id) -> None:
        """Updating state preserves variable values."""
        # Initial state
        state = WorkflowState(
            session_id=session_id,
            workflow_name="workflow1",
            step="step1",
            variables={"var1": "initial"},
        )
        state_manager.save_state(state)

        # Update step and add variable
        state.step = "step2"
        state.variables["var2"] = "added"
        state_manager.save_state(state)

        # Verify
        loaded = state_manager.get_state(session_id)
        assert loaded.step == "step2"
        assert loaded.variables == {"var1": "initial", "var2": "added"}

    def test_empty_variables_persisted(self, state_manager, session_id) -> None:
        """Empty variables dict is persisted correctly."""
        state = WorkflowState(
            session_id=session_id,
            workflow_name="workflow",
            step="step1",
            variables={},
        )
        state_manager.save_state(state)

        loaded = state_manager.get_state(session_id)
        assert loaded.variables == {}

    def test_variables_with_special_types(self, state_manager, session_id) -> None:
        """Variables with nested structures are serialized correctly."""
        state = WorkflowState(
            session_id=session_id,
            workflow_name="workflow",
            step="step1",
            variables={
                "list_val": [1, 2, {"nested": "dict"}],
                "dict_val": {"key": [1, 2, 3]},
                "null_val": None,
                "bool_val": True,
            },
        )
        state_manager.save_state(state)

        loaded = state_manager.get_state(session_id)
        assert loaded.variables["list_val"] == [1, 2, {"nested": "dict"}]
        assert loaded.variables["dict_val"] == {"key": [1, 2, 3]}
        assert loaded.variables["null_val"] is None
        assert loaded.variables["bool_val"] is True


# =============================================================================
# Test Variable Initialization from Definition
# =============================================================================


class TestWorkflowStateInitFromDefinition:
    """Tests for initializing WorkflowState variables from WorkflowDefinition."""

    def test_state_initialized_with_definition_variables(self) -> None:
        """WorkflowState should copy variables from WorkflowDefinition."""
        # This is the pattern used in agents/runner.py:327
        definition = WorkflowDefinition(
            name="test_workflow",
            variables={
                "require_task_before_edit": True,
                "tdd_mode": False,
                "session_task": None,
            },
        )

        # Pattern from agents/runner.py
        initial_variables = dict(definition.variables)

        state = WorkflowState(
            session_id="session_001",
            workflow_name=definition.name,
            step="step1",
            variables=initial_variables,
        )

        assert state.variables["require_task_before_edit"] is True
        assert state.variables["tdd_mode"] is False
        assert state.variables["session_task"] is None

    def test_state_runtime_variables_can_override_defaults(self) -> None:
        """Runtime variables set after initialization override definition defaults."""
        definition = WorkflowDefinition(
            name="test_workflow",
            variables={
                "require_task_before_edit": True,
                "tdd_mode": False,
            },
        )

        initial_variables = dict(definition.variables)
        state = WorkflowState(
            session_id="session_001",
            workflow_name=definition.name,
            step="step1",
            variables=initial_variables,
        )

        # Runtime override
        state.variables["require_task_before_edit"] = False
        state.variables["new_var"] = "runtime_value"

        assert state.variables["require_task_before_edit"] is False  # Overridden
        assert state.variables["tdd_mode"] is False  # From definition
        assert state.variables["new_var"] == "runtime_value"  # New

    def test_activate_workflow_does_not_copy_definition_variables(self) -> None:
        """Bug/gap: activate_workflow MCP tool initializes empty variables.

        This test documents current behavior - activate_workflow creates state
        with empty variables instead of copying from definition.
        """
        # Simulating what activate_workflow does (line 253 in workflows.py)
        state = WorkflowState(
            session_id="session_001",
            workflow_name="some_workflow",
            step="step1",
            step_entered_at=datetime.now(UTC),
            step_action_count=0,
            total_action_count=0,
            artifacts={},
            observations=[],
            reflection_pending=False,
            context_injected=False,
            variables={},  # Empty! Definition variables not copied
            task_list=None,
            current_task_index=0,
            files_modified_this_task=0,
        )

        # This documents the current gap - variables are empty
        assert state.variables == {}


# =============================================================================
# Test Variable Precedence Pattern
# =============================================================================


class TestVariablePrecedencePattern:
    """Tests for the explicit > workflow_variable > config default pattern.

    This pattern should be followed by configurable behaviors that can be
    set via explicit parameter, workflow variable, or config default.
    """

    def test_explicit_parameter_takes_precedence(self) -> None:
        """Explicit parameter overrides workflow variable and config default."""
        workflow_state = WorkflowState(
            session_id="s1",
            workflow_name="w1",
            step="step1",
            variables={"tdd_mode": False},  # Workflow says False
        )

        # Precedence pattern: explicit > workflow_variable > config default
        tdd_mode = True  # Explicit parameter
        if tdd_mode is not None:
            effective = tdd_mode
        elif workflow_state and workflow_state.variables.get("tdd_mode") is not None:
            effective = bool(workflow_state.variables.get("tdd_mode"))
        else:
            effective = True  # Config default

        assert effective is True  # Explicit wins

    def test_workflow_variable_overrides_config_default(self) -> None:
        """Workflow variable overrides config default when no explicit param."""
        workflow_state = WorkflowState(
            session_id="s1",
            workflow_name="w1",
            step="step1",
            variables={"tdd_mode": False},  # Workflow says False
        )

        tdd_mode = None  # No explicit parameter
        if tdd_mode is not None:
            effective = tdd_mode
        elif workflow_state and workflow_state.variables.get("tdd_mode") is not None:
            effective = bool(workflow_state.variables.get("tdd_mode"))
        else:
            effective = True  # Config default

        assert effective is False  # Workflow variable wins

    def test_config_default_used_when_no_override(self) -> None:
        """Config default is used when no explicit param or workflow variable."""
        workflow_state = WorkflowState(
            session_id="s1",
            workflow_name="w1",
            step="step1",
            variables={},  # No tdd_mode variable
        )

        tdd_mode = None  # No explicit parameter
        if tdd_mode is not None:
            effective = tdd_mode
        elif workflow_state and workflow_state.variables.get("tdd_mode") is not None:
            effective = bool(workflow_state.variables.get("tdd_mode"))
        else:
            effective = True  # Config default

        assert effective is True  # Config default wins

    def test_null_workflow_state_uses_config_default(self) -> None:
        """When workflow_state is None, config default is used."""
        workflow_state = None

        tdd_mode = None
        if tdd_mode is not None:
            effective = tdd_mode
        elif workflow_state and workflow_state.variables.get("tdd_mode") is not None:
            effective = bool(workflow_state.variables.get("tdd_mode"))
        else:
            effective = True  # Config default

        assert effective is True


# =============================================================================
# Test Session Variables via MCP Tools
# =============================================================================


class TestWorkflowMCPVariables:
    """Tests for workflow variable operations via MCP tools pattern."""

    @pytest.fixture
    def state_manager(self, temp_db):
        """Create WorkflowStateManager with test database (uses temp_db from conftest)."""
        return WorkflowStateManager(temp_db)

    @pytest.fixture
    def session_id(self, temp_db):
        """Create a session for FK constraint and return its ID."""
        from gobby.storage.projects import LocalProjectManager
        from gobby.storage.sessions import LocalSessionManager

        # Create project first
        project_manager = LocalProjectManager(temp_db)
        project = project_manager.get_or_create("/tmp/test-project")

        # Create session using register method
        session_manager = LocalSessionManager(temp_db)
        session = session_manager.register(
            external_id="ext_mcp_001",
            machine_id="machine_001",
            source="claude_code",
            project_id=project.id,
        )
        return session.id

    def test_set_variable_creates_lifecycle_state(self, state_manager, session_id) -> None:
        """Setting variable on session without state creates __lifecycle__ state.

        This is the pattern used by set_variable MCP tool (workflows.py:504-511).
        """
        # No existing state
        assert state_manager.get_state(session_id) is None

        # Pattern from set_variable tool
        state = state_manager.get_state(session_id)
        if not state:
            state = WorkflowState(
                session_id=session_id,
                workflow_name="__lifecycle__",
                step="",
                step_entered_at=datetime.now(UTC),
                variables={},
            )

        state.variables["session_task"] = "gt-abc123"
        state_manager.save_state(state)

        # Verify
        loaded = state_manager.get_state(session_id)
        assert loaded.workflow_name == "__lifecycle__"
        assert loaded.variables["session_task"] == "gt-abc123"

    def test_set_variable_updates_existing_state(self, state_manager, session_id) -> None:
        """Setting variable on existing state adds to existing variables."""
        # Create initial state with existing variable
        initial_state = WorkflowState(
            session_id=session_id,
            workflow_name="some_workflow",
            step="step1",
            variables={"existing_var": "existing_value"},
        )
        state_manager.save_state(initial_state)

        # Get and update
        state = state_manager.get_state(session_id)
        state.variables["new_var"] = "new_value"
        state_manager.save_state(state)

        # Verify both variables exist
        loaded = state_manager.get_state(session_id)
        assert loaded.variables["existing_var"] == "existing_value"
        assert loaded.variables["new_var"] == "new_value"

    def test_get_variable_returns_none_for_missing(self, state_manager, session_id) -> None:
        """Getting non-existent variable returns None."""
        state = WorkflowState(
            session_id=session_id,
            workflow_name="workflow",
            step="step1",
            variables={"exists": "value"},
        )
        state_manager.save_state(state)

        loaded = state_manager.get_state(session_id)
        assert loaded.variables.get("exists") == "value"
        assert loaded.variables.get("missing") is None
        assert loaded.variables.get("missing", "default") == "default"
