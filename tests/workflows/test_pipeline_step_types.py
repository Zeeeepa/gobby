"""Tests for spawn_session and activate_workflow pipeline step types."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestPipelineStepValidation:
    """Tests for PipelineStep accepting spawn_session and activate_workflow."""

    def test_spawn_session_step_accepted(self) -> None:
        """PipelineStep accepts spawn_session as a valid execution type."""
        from gobby.workflows.definitions import PipelineStep

        step = PipelineStep(
            id="spawn",
            spawn_session={"cli": "claude", "prompt": "Do work"},
        )
        assert step.spawn_session is not None
        assert step.spawn_session["cli"] == "claude"

    def test_activate_workflow_step_accepted(self) -> None:
        """PipelineStep accepts activate_workflow as a valid execution type."""
        from gobby.workflows.definitions import PipelineStep

        step = PipelineStep(
            id="activate",
            activate_workflow={"name": "auto-task", "variables": {"x": 1}},
        )
        assert step.activate_workflow is not None
        assert step.activate_workflow["name"] == "auto-task"

    def test_spawn_session_mutually_exclusive_with_exec(self) -> None:
        """spawn_session cannot be combined with exec."""
        from gobby.workflows.definitions import PipelineStep

        with pytest.raises(ValueError, match="mutually exclusive"):
            PipelineStep(
                id="bad",
                exec="ls",
                spawn_session={"cli": "claude"},
            )

    def test_activate_workflow_mutually_exclusive_with_prompt(self) -> None:
        """activate_workflow cannot be combined with prompt."""
        from gobby.workflows.definitions import PipelineStep

        with pytest.raises(ValueError, match="mutually exclusive"):
            PipelineStep(
                id="bad",
                prompt="Do something",
                activate_workflow={"name": "test"},
            )


class TestSpawnSessionExecution:
    """Tests for spawn_session step execution in pipeline executor."""

    @pytest.mark.asyncio
    async def test_spawn_session_creates_session(self) -> None:
        """spawn_session step creates a session via spawner."""
        from gobby.workflows.definitions import PipelineDefinition, PipelineStep
        from gobby.workflows.pipeline_executor import PipelineExecutor
        from gobby.workflows.pipeline_state import ExecutionStatus

        mock_db = MagicMock()
        mock_exec_mgr = MagicMock()
        mock_exec_mgr.create_execution.return_value = MagicMock(
            id="pe-1",
            pipeline_name="test",
            project_id="proj-1",
            status=ExecutionStatus.RUNNING,
            steps={},
        )
        mock_exec_mgr.update_execution = MagicMock()

        mock_spawner = MagicMock()
        mock_spawner.spawn_agent.return_value = MagicMock(
            session_id="spawned-sess-1",
            tmux_session_name="gobby-claude-d1",
        )

        mock_session_mgr = MagicMock()
        mock_session_mgr.create_session.return_value = MagicMock(id="spawned-sess-1")

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_exec_mgr,
            llm_service=MagicMock(),
            spawner=mock_spawner,
            session_manager=mock_session_mgr,
        )

        step = PipelineStep(
            id="spawn-worker",
            spawn_session={"cli": "claude", "prompt": "Fix the bug"},
        )

        result = await executor._execute_step(
            step, {"inputs": {}, "steps": {}, "env": {}}, "proj-1"
        )

        assert result is not None
        assert "session_id" in result
        mock_spawner.spawn_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_spawn_session_fails_without_spawner(self) -> None:
        """spawn_session returns error when spawner not configured."""
        from gobby.workflows.definitions import PipelineStep
        from gobby.workflows.pipeline_executor import PipelineExecutor

        executor = PipelineExecutor(
            db=MagicMock(),
            execution_manager=MagicMock(),
            llm_service=MagicMock(),
        )

        step = PipelineStep(
            id="spawn",
            spawn_session={"cli": "claude"},
        )

        result = await executor._execute_step(
            step, {"inputs": {}, "steps": {}, "env": {}}, "proj-1"
        )

        assert result is not None
        assert "error" in result


class TestActivateWorkflowExecution:
    """Tests for activate_workflow step execution in pipeline executor."""

    @pytest.mark.asyncio
    async def test_activate_workflow_step_activates(self) -> None:
        """activate_workflow step activates workflow via loader."""
        from gobby.workflows.definitions import (
            PipelineStep,
            WorkflowDefinition,
            WorkflowStep,
        )
        from gobby.workflows.pipeline_executor import PipelineExecutor

        definition = WorkflowDefinition(
            name="auto-task",
            type="step",
            steps=[WorkflowStep(name="start"), WorkflowStep(name="work")],
            variables={},
            session_variables={},
        )
        mock_loader = MagicMock()
        mock_loader.load_workflow = AsyncMock(return_value=definition)

        mock_session_mgr = MagicMock()
        mock_session_mgr.resolve_session_reference.return_value = "uuid-sess-1"

        executor = PipelineExecutor(
            db=MagicMock(),
            execution_manager=MagicMock(),
            llm_service=MagicMock(),
            loader=mock_loader,
            session_manager=mock_session_mgr,
        )

        step = PipelineStep(
            id="activate",
            activate_workflow={
                "name": "auto-task",
                "session_id": "uuid-sess-1",
                "variables": {"task": "fix-bug"},
            },
        )

        result = await executor._execute_step(
            step, {"inputs": {}, "steps": {}, "env": {}}, "proj-1"
        )

        assert result is not None
        assert result.get("success") is True
        assert result["workflow"] == "auto-task"

    @pytest.mark.asyncio
    async def test_activate_workflow_fails_without_loader(self) -> None:
        """activate_workflow returns error when loader not configured."""
        from gobby.workflows.definitions import PipelineStep
        from gobby.workflows.pipeline_executor import PipelineExecutor

        executor = PipelineExecutor(
            db=MagicMock(),
            execution_manager=MagicMock(),
            llm_service=MagicMock(),
        )

        step = PipelineStep(
            id="activate",
            activate_workflow={"name": "test-wf", "session_id": "sess-1"},
        )

        result = await executor._execute_step(
            step, {"inputs": {}, "steps": {}, "env": {}}, "proj-1"
        )

        assert result is not None
        assert "error" in result
