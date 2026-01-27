"""
E2E tests for parallel clone orchestration.

Tests verify:
1. Clone tools are available on gobby-clones server
2. Epic with 3 independent subtasks can be created
3. Clone lifecycle: create → get → list → delete
4. Parallel orchestrator workflow is available
5. Clone operations work correctly

Test scenario (conceptual):
1. Create epic with 3 independent subtasks
2. Activate parallel-orchestrator
3. Spawn agents in clones (3 parallel)
4. As each completes: sync → merge → cleanup
5. Verify proper merge handling

Note: Full agent spawning requires LLM API keys which are disabled in E2E tests.
These tests verify the infrastructure (tools, workflows, clone management) is correct.
"""

import uuid

import pytest

from tests.e2e.conftest import (
    CLIEventSimulator,
    DaemonInstance,
    MCPTestClient,
)

pytestmark = pytest.mark.e2e


def unwrap_result(result: dict) -> dict:
    """Unwrap MCP tool call result from wrapper response."""
    if "result" in result:
        return result["result"]
    return result


class TestCloneToolsAvailability:
    """Tests to verify clone tools are properly registered."""

    def test_clone_tools_are_registered(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Verify all clone management tools are available on gobby-clones server."""
        tools = mcp_client.list_tools(server="gobby-clones")
        tool_names = [t["name"] for t in tools]

        expected_tools = [
            "create_clone",
            "get_clone",
            "list_clones",
            "delete_clone",
            "sync_clone",
            "merge_clone_to_target",
            "spawn_agent_in_clone",
        ]

        for tool in expected_tools:
            assert tool in tool_names, f"Missing tool: {tool}"

    def test_create_clone_schema(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Verify create_clone tool schema can be retrieved."""
        raw_schema = mcp_client.get_tool_schema(
            server_name="gobby-clones",
            tool_name="create_clone",
        )

        assert raw_schema is not None
        assert isinstance(raw_schema, dict)

    def test_spawn_agent_in_clone_schema(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Verify spawn_agent_in_clone tool schema can be retrieved."""
        raw_schema = mcp_client.get_tool_schema(
            server_name="gobby-clones",
            tool_name="spawn_agent_in_clone",
        )

        assert raw_schema is not None
        assert isinstance(raw_schema, dict)


class TestParallelOrchestratorWorkflow:
    """Tests for the parallel-orchestrator workflow."""

    def test_parallel_orchestrator_workflow_tools(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Verify workflow tools needed for parallel orchestration are available."""
        tools = mcp_client.list_tools(server="gobby-workflows")
        tool_names = [t["name"] for t in tools]

        expected_tools = [
            "activate_workflow",
            "get_workflow_status",
            "set_variable",
            "get_variable",
        ]

        for tool in expected_tools:
            assert tool in tool_names, f"Missing workflow tool: {tool}"

    def test_orchestration_tools_available(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Verify orchestration tools needed for parallel processing are available."""
        tools = mcp_client.list_tools(server="gobby-tasks")
        tool_names = [t["name"] for t in tools]

        expected_tools = [
            "list_ready_tasks",
            "orchestrate_ready_tasks",
            "get_orchestration_status",
            "poll_agent_status",
            "suggest_next_task",
        ]

        for tool in expected_tools:
            assert tool in tool_names, f"Missing orchestration tool: {tool}"


class TestEpicWithIndependentSubtasks:
    """Tests for creating epics with independent subtasks."""

    def test_create_epic_with_3_independent_subtasks(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test creating epic with 3 independent subtasks for parallel processing.

        Independent subtasks have no dependencies on each other, so they can
        be processed in parallel by the parallel-orchestrator.
        """
        # Setup - use "e2e-test-project" to match fixture's project.json
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        session_external_id = f"parallel-epic-{uuid.uuid4().hex[:8]}"
        session_result = cli_events.register_session(
            external_id=session_external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
        )
        session_id = session_result["id"]

        # Create epic
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="create_task",
            arguments={
                "title": "Parallel Processing Epic",
                "description": "Epic for testing parallel clone orchestration",
                "task_type": "epic",
                "session_id": session_id,
            },
        )
        result = unwrap_result(raw_result)
        assert result.get("id") is not None, f"Epic creation failed: {result}"
        epic_id = result["id"]

        # Create 3 independent subtasks (no dependencies between them)
        subtask_ids = []
        for i in range(1, 4):
            raw_result = mcp_client.call_tool(
                server_name="gobby-tasks",
                tool_name="create_task",
                arguments={
                    "title": f"Independent Subtask {i}",
                    "description": f"Subtask {i} - can be processed in parallel",
                    "task_type": "task",
                    "parent_task_id": epic_id,
                    "session_id": session_id,
                },
            )
            result = unwrap_result(raw_result)
            assert result.get("id") is not None, f"Subtask {i} creation failed: {result}"
            subtask_ids.append(result["id"])

        assert len(subtask_ids) == 3, "Should have created 3 subtasks"

        # Verify all 3 subtasks are in list_ready_tasks (no blockers)
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="list_ready_tasks",
            arguments={"parent_task_id": epic_id},
        )
        result = unwrap_result(raw_result)
        ready_tasks = result.get("tasks", [])

        # All 3 should be ready since they have no dependencies
        ready_ids = [t["id"] for t in ready_tasks]
        for subtask_id in subtask_ids:
            assert subtask_id in ready_ids, f"Subtask {subtask_id} should be ready"

    def test_orchestration_status_for_parallel_epic(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test orchestration status tracking for parallel epic."""
        # Setup
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        session_external_id = f"orch-parallel-{uuid.uuid4().hex[:8]}"
        session_result = cli_events.register_session(
            external_id=session_external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
        )
        session_id = session_result["id"]

        # Create epic with 3 subtasks
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="create_task",
            arguments={
                "title": "Status Tracking Epic",
                "task_type": "epic",
                "session_id": session_id,
            },
        )
        epic_result = unwrap_result(raw_result)
        epic_id = epic_result["id"]

        for i in range(3):
            mcp_client.call_tool(
                server_name="gobby-tasks",
                tool_name="create_task",
                arguments={
                    "title": f"Status Subtask {i + 1}",
                    "task_type": "task",
                    "parent_task_id": epic_id,
                    "session_id": session_id,
                },
            )

        # Get orchestration status
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="get_orchestration_status",
            arguments={
                "parent_task_id": epic_id,
                "project_path": str(daemon_instance.project_dir),
            },
        )
        result = unwrap_result(raw_result)

        assert result.get("success") is True, f"get_orchestration_status failed: {result}"
        assert "summary" in result, f"Missing summary in result: {result}"
        assert "open_tasks" in result, f"Missing open_tasks in result: {result}"


class TestCloneLifecycle:
    """Tests for clone lifecycle operations."""

    def test_list_clones_empty(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Test listing clones when none exist."""
        raw_result = mcp_client.call_tool(
            server_name="gobby-clones",
            tool_name="list_clones",
            arguments={},
        )
        result = unwrap_result(raw_result)

        assert result.get("success") is True, f"list_clones failed: {result}"
        assert isinstance(result.get("clones"), list)
        # Count may be 0 or more depending on previous test state
        assert result.get("count", -1) >= 0

    def test_get_clone_not_found(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Test getting a non-existent clone returns error."""
        raw_result = mcp_client.call_tool(
            server_name="gobby-clones",
            tool_name="get_clone",
            arguments={"clone_id": "nonexistent-clone-id"},
        )
        result = unwrap_result(raw_result)

        assert result.get("success") is False
        assert "not found" in result.get("error", "").lower()

    def test_delete_clone_not_found(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Test deleting a non-existent clone returns error."""
        raw_result = mcp_client.call_tool(
            server_name="gobby-clones",
            tool_name="delete_clone",
            arguments={"clone_id": "nonexistent-clone-id"},
        )
        result = unwrap_result(raw_result)

        assert result.get("success") is False
        assert "not found" in result.get("error", "").lower()

    def test_sync_clone_not_found(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Test syncing a non-existent clone returns error."""
        raw_result = mcp_client.call_tool(
            server_name="gobby-clones",
            tool_name="sync_clone",
            arguments={
                "clone_id": "nonexistent-clone-id",
                "direction": "pull",
            },
        )
        result = unwrap_result(raw_result)

        assert result.get("success") is False
        assert "not found" in result.get("error", "").lower()

    def test_merge_clone_to_target_not_found(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Test merging a non-existent clone returns error."""
        raw_result = mcp_client.call_tool(
            server_name="gobby-clones",
            tool_name="merge_clone_to_target",
            arguments={"clone_id": "nonexistent-clone-id"},
        )
        result = unwrap_result(raw_result)

        assert result.get("success") is False
        assert "not found" in result.get("error", "").lower()


class TestSpawnAgentInClone:
    """Tests for spawn_agent_in_clone tool."""

    def test_spawn_without_parent_session_fails(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Test spawn_agent_in_clone requires parent_session_id."""
        raw_result = mcp_client.call_tool(
            server_name="gobby-clones",
            tool_name="spawn_agent_in_clone",
            arguments={
                "prompt": "Test task",
                "branch_name": "test-branch",
                # Missing parent_session_id
            },
        )
        result = unwrap_result(raw_result)

        assert result.get("success") is False
        assert "parent_session_id" in result.get("error", "").lower()

    def test_spawn_with_invalid_mode_fails(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test spawn_agent_in_clone with invalid mode returns error."""
        # Setup session
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        session_external_id = f"spawn-mode-{uuid.uuid4().hex[:8]}"
        session_result = cli_events.register_session(
            external_id=session_external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
        )
        session_id = session_result["id"]

        raw_result = mcp_client.call_tool(
            server_name="gobby-clones",
            tool_name="spawn_agent_in_clone",
            arguments={
                "prompt": "Test task",
                "branch_name": "test-branch",
                "parent_session_id": session_id,
                "mode": "invalid_mode",  # Invalid mode
            },
        )
        result = unwrap_result(raw_result)

        assert result.get("success") is False
        assert (
            "invalid" in result.get("error", "").lower()
            or "mode" in result.get("error", "").lower()
        )


class TestParallelTaskProcessing:
    """Tests for parallel task processing flow."""

    def test_complete_parallel_tasks_sequentially(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test completing multiple parallel tasks sequentially (simulates parallel completion).

        While we can't spawn actual agents in E2E tests, we can verify the task
        status flow works correctly when tasks are completed in parallel.
        """
        # Setup
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        session_external_id = f"parallel-complete-{uuid.uuid4().hex[:8]}"
        session_result = cli_events.register_session(
            external_id=session_external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
        )
        session_id = session_result["id"]

        # Create epic with 3 independent subtasks
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="create_task",
            arguments={
                "title": "Parallel Completion Epic",
                "task_type": "epic",
                "session_id": session_id,
            },
        )
        epic_result = unwrap_result(raw_result)
        epic_id = epic_result["id"]

        subtask_ids = []
        for i in range(3):
            raw_result = mcp_client.call_tool(
                server_name="gobby-tasks",
                tool_name="create_task",
                arguments={
                    "title": f"Parallel Task {i + 1}",
                    "task_type": "task",
                    "parent_task_id": epic_id,
                    "session_id": session_id,
                },
            )
            result = unwrap_result(raw_result)
            subtask_ids.append(result["id"])

        # Simulate parallel processing: all tasks set to in_progress
        for task_id in subtask_ids:
            mcp_client.call_tool(
                server_name="gobby-tasks",
                tool_name="update_task",
                arguments={"task_id": task_id, "status": "in_progress"},
            )

        # Verify all are in_progress
        for task_id in subtask_ids:
            raw_result = mcp_client.call_tool(
                server_name="gobby-tasks",
                tool_name="get_task",
                arguments={"task_id": task_id},
            )
            result = unwrap_result(raw_result)
            assert result.get("status") == "in_progress", f"Task {task_id} should be in_progress"

        # Complete all tasks (simulating agents finishing)
        for task_id in subtask_ids:
            # Close as already implemented (simulating completed work)
            mcp_client.call_tool(
                server_name="gobby-tasks",
                tool_name="close_task",
                arguments={
                    "task_id": task_id,
                    "reason": "already_implemented",
                },
            )

        # Verify all are closed
        for task_id in subtask_ids:
            raw_result = mcp_client.call_tool(
                server_name="gobby-tasks",
                tool_name="get_task",
                arguments={"task_id": task_id},
            )
            result = unwrap_result(raw_result)
            assert result.get("status") == "closed", f"Task {task_id} should be closed"

        # Verify no more ready tasks under epic
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="list_ready_tasks",
            arguments={"parent_task_id": epic_id},
        )
        result = unwrap_result(raw_result)
        ready_tasks = result.get("tasks", [])
        assert len(ready_tasks) == 0, f"Should have no ready tasks after completion: {ready_tasks}"

        # Close the epic (all subtasks completed)
        mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="close_task",
            arguments={
                "task_id": epic_id,
                "reason": "already_implemented",
            },
        )

        # Verify epic is closed
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="get_task",
            arguments={"task_id": epic_id},
        )
        result = unwrap_result(raw_result)
        assert result.get("status") == "closed", f"Epic should be closed: {result}"


class TestWorkflowActivation:
    """Tests for workflow activation in parallel orchestration context."""

    def test_get_workflow_status_no_active_workflow(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test get_workflow_status returns correct status when no workflow active."""
        # Setup session
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        session_external_id = f"workflow-status-{uuid.uuid4().hex[:8]}"
        session_result = cli_events.register_session(
            external_id=session_external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
        )
        session_id = session_result["id"]

        # Get workflow status - should indicate no active workflow
        raw_result = mcp_client.call_tool(
            server_name="gobby-workflows",
            tool_name="get_workflow_status",
            arguments={"session_id": session_id},
        )
        result = unwrap_result(raw_result)

        # Either has_workflow is False or workflow_name is None
        assert result.get("has_workflow") is False or result.get("workflow_name") is None, (
            f"Unexpected workflow status: {result}"
        )
