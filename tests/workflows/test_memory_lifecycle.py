"""Integration tests for memory injection at session_start via lifecycle workflow."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.memory.manager import MemoryManager
from gobby.storage.sessions import LocalSessionManager
from gobby.workflows.actions import ActionExecutor
from gobby.workflows.engine import WorkflowEngine
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager
from gobby.workflows.templates import TemplateEngine


@pytest.fixture
def template_workflow_dir(temp_dir: Path) -> Path:
    """Create workflow directory with memory-lifecycle.yaml in lifecycle/ subdir."""
    workflow_dir = temp_dir / "workflows"
    workflow_dir.mkdir()

    # Lifecycle workflows must be in the lifecycle/ subdirectory
    lifecycle_dir = workflow_dir / "lifecycle"
    lifecycle_dir.mkdir()

    # Copy the actual memory-lifecycle workflow
    memory_lifecycle = lifecycle_dir / "memory-lifecycle.yaml"
    memory_lifecycle.write_text("""
name: memory-lifecycle
description: Standard memory lifecycle hooks
version: "1.0"
type: lifecycle
author: Gobby
settings:
  priority: 50

triggers:
  on_session_start:
    - action: memory_inject
      min_importance: 0.5

  on_session_end:
    - action: skills_learn
""")
    return workflow_dir


@pytest.fixture
def workflow_loader(template_workflow_dir: Path) -> WorkflowLoader:
    """Create workflow loader with test workflow directory."""
    return WorkflowLoader(workflow_dirs=[template_workflow_dir])


@pytest.fixture
def mock_memory_manager():
    """Create a mock memory manager with enabled config."""
    mm = MagicMock(spec=MemoryManager)
    mm.config = MagicMock()
    mm.config.enabled = True
    return mm


@pytest.fixture
def action_executor_with_memory(temp_db, session_manager, mock_memory_manager) -> ActionExecutor:
    """Create ActionExecutor with memory_manager wired up."""
    return ActionExecutor(
        db=temp_db,
        session_manager=session_manager,
        template_engine=MagicMock(spec=TemplateEngine),
        llm_service=AsyncMock(),
        transcript_processor=MagicMock(),
        config=MagicMock(),
        mcp_manager=AsyncMock(),
        memory_manager=mock_memory_manager,
        skill_learner=AsyncMock(),
        memory_sync_manager=AsyncMock(),
    )


@pytest.fixture
def workflow_engine_with_memory(workflow_loader, action_executor_with_memory) -> WorkflowEngine:
    """Create WorkflowEngine with memory-capable ActionExecutor."""
    state_manager = MagicMock(spec=WorkflowStateManager)
    state_manager.get_state.return_value = None
    return WorkflowEngine(
        loader=workflow_loader,
        state_manager=state_manager,
        action_executor=action_executor_with_memory,
    )


class TestMemoryLifecycleDiscovery:
    """Test that memory-lifecycle workflow is properly discovered."""

    def test_discover_memory_lifecycle_workflow(self, workflow_loader: WorkflowLoader):
        """Verify memory-lifecycle is discovered as a lifecycle workflow."""
        workflows = workflow_loader.discover_lifecycle_workflows()

        assert len(workflows) == 1
        assert workflows[0].name == "memory-lifecycle"
        assert workflows[0].definition.type == "lifecycle"
        assert workflows[0].priority == 50

    def test_memory_lifecycle_has_session_start_trigger(self, workflow_loader: WorkflowLoader):
        """Verify memory-lifecycle has on_session_start trigger."""
        workflow = workflow_loader.load_workflow("memory-lifecycle")

        assert workflow is not None
        assert workflow.triggers is not None
        assert "on_session_start" in workflow.triggers

        triggers = workflow.triggers["on_session_start"]
        assert len(triggers) == 1
        assert triggers[0]["action"] == "memory_inject"
        assert triggers[0].get("min_importance") == 0.5


class TestMemoryInjectAtSessionStart:
    """Test memory injection triggered by session_start event."""

    @pytest.mark.asyncio
    async def test_memory_inject_triggered_on_session_start(
        self,
        workflow_engine_with_memory: WorkflowEngine,
        mock_memory_manager,
        session_manager: LocalSessionManager,
        sample_project,
    ):
        """Verify memory_inject action is called when session_start fires."""
        # Create a session
        session = session_manager.register(
            external_id="test-ext-id",
            machine_id="test-machine",
            source="claude",
            project_id=sample_project["id"],
        )

        # Setup mock memories
        mock_memory = MagicMock()
        mock_memory.memory_type = "fact"
        mock_memory.content = "Test fact about the project"
        mock_memory_manager.recall.return_value = [mock_memory]

        # Create session_start event
        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id=session.id,
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"cwd": "/tmp/test-project"},
            metadata={"_platform_session_id": session.id},
        )

        # Evaluate lifecycle triggers
        await workflow_engine_with_memory.evaluate_all_lifecycle_workflows(event)

        # Verify memory_inject was called
        mock_memory_manager.recall.assert_called_once()
        call_kwargs = mock_memory_manager.recall.call_args[1]
        assert call_kwargs["min_importance"] == 0.5

    @pytest.mark.asyncio
    async def test_memory_context_injected_in_response(
        self,
        workflow_engine_with_memory: WorkflowEngine,
        mock_memory_manager,
        session_manager: LocalSessionManager,
        sample_project,
    ):
        """Verify memory context appears in HookResponse.context."""
        # Create a session
        session = session_manager.register(
            external_id="test-ext-id-2",
            machine_id="test-machine",
            source="claude",
            project_id=sample_project["id"],
        )

        # Setup mock memories with different types
        fact_memory = MagicMock()
        fact_memory.memory_type = "fact"
        fact_memory.content = "Project uses Python 3.11"

        preference_memory = MagicMock()
        preference_memory.memory_type = "preference"
        preference_memory.content = "User prefers pytest over unittest"

        mock_memory_manager.recall.return_value = [fact_memory, preference_memory]

        # Create session_start event
        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id=session.id,
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"cwd": "/tmp/test-project"},
            metadata={"_platform_session_id": session.id},
        )

        # Evaluate lifecycle triggers
        response = await workflow_engine_with_memory.evaluate_all_lifecycle_workflows(event)

        # Verify response contains injected context
        assert response.context is not None
        assert "<project-memory>" in response.context
        assert "Project uses Python 3.11" in response.context
        assert "User prefers pytest over unittest" in response.context

    @pytest.mark.asyncio
    async def test_no_memories_returns_no_context(
        self,
        workflow_engine_with_memory: WorkflowEngine,
        mock_memory_manager,
        session_manager: LocalSessionManager,
        sample_project,
    ):
        """Verify no context is injected when no memories exist."""
        session = session_manager.register(
            external_id="test-ext-id-3",
            machine_id="test-machine",
            source="claude",
            project_id=sample_project["id"],
        )

        # No memories
        mock_memory_manager.recall.return_value = []

        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id=session.id,
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"cwd": "/tmp/test-project"},
            metadata={"_platform_session_id": session.id},
        )

        response = await workflow_engine_with_memory.evaluate_all_lifecycle_workflows(event)

        # Should still allow, just no context
        assert response.decision == "allow"
        # Context should be None or empty when no memories
        assert response.context is None or response.context == ""

    @pytest.mark.asyncio
    async def test_memory_injection_disabled_via_workflow_variable(
        self,
        workflow_loader,
        action_executor_with_memory,
        mock_memory_manager,
        session_manager: LocalSessionManager,
        sample_project,
    ):
        """Verify memory injection is skipped when workflow variable disables it."""
        session = session_manager.register(
            external_id="test-ext-id-4",
            machine_id="test-machine",
            source="claude",
            project_id=sample_project["id"],
        )

        # Create state manager that returns state with memory_injection_enabled=false
        state_manager = MagicMock(spec=WorkflowStateManager)
        mock_state = MagicMock()
        mock_state.variables = {"memory_injection_enabled": False}
        state_manager.get_state.return_value = mock_state

        workflow_engine = WorkflowEngine(
            loader=workflow_loader,
            state_manager=state_manager,
            action_executor=action_executor_with_memory,
        )

        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id=session.id,
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC),
            data={"cwd": "/tmp/test-project"},
            metadata={"_platform_session_id": session.id},
        )

        response = await workflow_engine.evaluate_all_lifecycle_workflows(event)

        # recall should not be called when disabled via workflow variable
        mock_memory_manager.recall.assert_not_called()
        assert response.decision == "allow"


class TestMemoryLifecyclePriority:
    """Test that memory-lifecycle runs with correct priority."""

    def test_memory_lifecycle_priority_is_50(self, workflow_loader: WorkflowLoader):
        """Verify memory-lifecycle has priority 50 (runs before default 100)."""
        workflows = workflow_loader.discover_lifecycle_workflows()

        memory_wf = next(w for w in workflows if w.name == "memory-lifecycle")
        assert memory_wf.priority == 50

    def test_memory_lifecycle_runs_before_default_priority(
        self, temp_dir: Path, workflow_loader: WorkflowLoader
    ):
        """Verify memory-lifecycle runs before default-priority workflows."""
        # Add another lifecycle workflow with default priority (in lifecycle/ subdir)
        lifecycle_dir = temp_dir / "workflows" / "lifecycle"
        other_workflow = lifecycle_dir / "other-lifecycle.yaml"
        other_workflow.write_text("""
name: other-lifecycle
type: lifecycle
triggers:
  on_session_start:
    - action: inject_context
      content: "Other context"
""")

        # Clear cache and rediscover
        workflow_loader.clear_discovery_cache()
        workflows = workflow_loader.discover_lifecycle_workflows()

        assert len(workflows) == 2

        # memory-lifecycle (priority 50) should come before other (priority 100)
        assert workflows[0].name == "memory-lifecycle"
        assert workflows[0].priority == 50
        assert workflows[1].name == "other-lifecycle"
        assert workflows[1].priority == 100
