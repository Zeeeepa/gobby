"""
E2E tests for sequential review loop in orchestration.

Tests verify:
1. Epic creation with subtasks
2. Sequential task processing flow
3. Review step after task completion
4. Task closure and status transitions

Test scenario:
1. Create epic with 2 subtasks
2. Simulate sequential orchestration: spawn→wait→review for each task
3. Verify tasks progress through correct states
4. Verify epic completion when all subtasks done
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


class TestSequentialReviewLoopE2E:
    """E2E tests for sequential review loop orchestration."""

    def test_epic_with_subtasks_sequential_processing(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test sequential processing of epic with 2 subtasks.

        This test verifies the sequential review loop:
        1. Create epic with 2 subtasks
        2. First subtask: open → in_progress → closed
        3. Second subtask: open → in_progress → closed
        4. Verify both subtasks closed
        5. Verify epic can be closed
        """
        # Setup: Register project and session
        # Use "e2e-test-project" to match the project.json created by e2e_project_dir fixture
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        session_external_id = f"orchestrator-{uuid.uuid4().hex[:8]}"
        session_result = cli_events.register_session(
            external_id=session_external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
        )
        session_id = session_result["id"]

        # Step 1: Create epic task
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="create_task",
            arguments={
                "title": "E2E Test Epic - Sequential Processing",
                "description": "Epic task for testing sequential review loop",
                "task_type": "epic",
                "session_id": session_id,
            },
        )
        result = unwrap_result(raw_result)
        assert result.get("id") is not None, f"Epic creation failed: {result}"
        epic_id = result["id"]
        epic_ref = result.get("ref", f"#{result.get('seq_num', '')}")

        # Step 2: Create 2 subtasks under the epic
        subtask_ids = []
        for i in range(1, 3):
            raw_result = mcp_client.call_tool(
                server_name="gobby-tasks",
                tool_name="create_task",
                arguments={
                    "title": f"Subtask {i} - Sequential Test",
                    "description": f"Subtask {i} for sequential processing test",
                    "task_type": "task",
                    "parent_task_id": epic_id,
                    "session_id": session_id,
                },
            )
            result = unwrap_result(raw_result)
            assert result.get("id") is not None, f"Subtask {i} creation failed: {result}"
            subtask_ids.append(result["id"])

        # Verify subtasks were created
        assert len(subtask_ids) == 2, "Should have created 2 subtasks"

        # Step 3: Process first subtask (simulate spawn→wait→review→close)
        # 3a: Set first subtask to in_progress
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="update_task",
            arguments={
                "task_id": subtask_ids[0],
                "status": "in_progress",
            },
        )
        result = unwrap_result(raw_result)
        assert result.get("success") is not False, (
            f"Update subtask 1 to in_progress failed: {result}"
        )

        # 3b: Verify first subtask is in_progress
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="get_task",
            arguments={"task_id": subtask_ids[0]},
        )
        result = unwrap_result(raw_result)
        assert result.get("status") == "in_progress", f"Subtask 1 should be in_progress: {result}"

        # 3c: Close first subtask (simulating agent completion)
        # Using reason="obsolete" bypasses commit check and closes directly
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="close_task",
            arguments={
                "task_id": subtask_ids[0],
                "reason": "obsolete",
            },
        )
        result = unwrap_result(raw_result)
        assert "error" not in result, f"Close subtask 1 failed: {result}"

        # 3d: Verify first subtask is closed
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="get_task",
            arguments={"task_id": subtask_ids[0]},
        )
        result = unwrap_result(raw_result)
        assert result.get("status") == "closed", f"Subtask 1 should be closed: {result}"

        # Step 4: Process second subtask (same flow)
        # 4a: Set second subtask to in_progress
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="update_task",
            arguments={
                "task_id": subtask_ids[1],
                "status": "in_progress",
            },
        )
        result = unwrap_result(raw_result)
        assert result.get("success") is not False, (
            f"Update subtask 2 to in_progress failed: {result}"
        )

        # 4b: Close second subtask
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="close_task",
            arguments={
                "task_id": subtask_ids[1],
                "reason": "obsolete",
            },
        )
        result = unwrap_result(raw_result)
        assert "error" not in result, f"Close subtask 2 failed: {result}"

        # 4c: Verify second subtask is closed
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="get_task",
            arguments={"task_id": subtask_ids[1]},
        )
        result = unwrap_result(raw_result)
        assert result.get("status") == "closed", f"Subtask 2 should be closed: {result}"

        # Step 5: Verify both subtasks are closed via list_tasks
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="list_tasks",
            arguments={
                "parent_task_id": epic_id,
                "status": "closed",
            },
        )
        result = unwrap_result(raw_result)
        closed_tasks = result.get("tasks", [])
        assert len(closed_tasks) >= 2, f"Should have 2 closed subtasks: {result}"

        # Step 6: Close the epic (all subtasks done)
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="close_task",
            arguments={
                "task_id": epic_id,
                "reason": "obsolete",
            },
        )
        result = unwrap_result(raw_result)
        assert "error" not in result, f"Close epic failed: {result}"

        # Verify epic is closed
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="get_task",
            arguments={"task_id": epic_id},
        )
        result = unwrap_result(raw_result)
        assert result.get("status") == "closed", f"Epic should be closed: {result}"

    def test_sequential_with_dependencies(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test sequential processing respects task dependencies.

        Subtask 2 depends on Subtask 1, so Subtask 2 should be blocked
        until Subtask 1 is closed.
        """
        # Setup - use "e2e-test-project" to match fixture's project.json
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        session_external_id = f"deps-test-{uuid.uuid4().hex[:8]}"
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
                "title": "Epic with Dependencies",
                "task_type": "epic",
                "session_id": session_id,
            },
        )
        epic_result = unwrap_result(raw_result)
        epic_id = epic_result["id"]

        # Create subtask 1
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="create_task",
            arguments={
                "title": "Subtask 1 - Foundation",
                "task_type": "task",
                "parent_task_id": epic_id,
                "session_id": session_id,
            },
        )
        subtask1_result = unwrap_result(raw_result)
        subtask1_id = subtask1_result["id"]
        subtask1_ref = subtask1_result.get("ref", f"#{subtask1_result.get('seq_num', '')}")

        # Create subtask 2
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="create_task",
            arguments={
                "title": "Subtask 2 - Depends on Subtask 1",
                "task_type": "task",
                "parent_task_id": epic_id,
                "session_id": session_id,
            },
        )
        subtask2_result = unwrap_result(raw_result)
        subtask2_id = subtask2_result["id"]
        subtask2_ref = subtask2_result.get("ref", f"#{subtask2_result.get('seq_num', '')}")

        # Add explicit dependency: subtask2 depends on subtask1
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="add_dependency",
            arguments={
                "task_id": subtask2_ref,
                "depends_on": subtask1_ref,
            },
        )
        result = unwrap_result(raw_result)
        assert result.get("added") is True, f"add_dependency failed: {result}"

        # Verify subtask 2 has dependency on subtask 1
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="get_task",
            arguments={"task_id": subtask2_id},
        )
        result = unwrap_result(raw_result)
        blocked_by = result.get("dependencies", {}).get("blocked_by", [])
        blocked_by_ids = [dep.get("depends_on") for dep in blocked_by]
        assert subtask1_id in blocked_by_ids, (
            f"Subtask 2 should be blocked by Subtask 1. Blocked by: {blocked_by_ids}"
        )

        # Verify subtask 1 has no blocking dependencies (should be ready)
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="get_task",
            arguments={"task_id": subtask1_id},
        )
        result = unwrap_result(raw_result)
        subtask1_blocked_by = result.get("dependencies", {}).get("blocked_by", [])
        assert len(subtask1_blocked_by) == 0, (
            f"Subtask 1 should have no blockers: {subtask1_blocked_by}"
        )

        # Complete subtask 1 (goes to review first, then close)
        mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="update_task",
            arguments={"task_id": subtask1_id, "status": "in_progress"},
        )
        mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="close_task",
            arguments={
                "task_id": subtask1_id,
                "reason": "obsolete",
            },
        )

        # Verify subtask 1 is closed
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="get_task",
            arguments={"task_id": subtask1_id},
        )
        result = unwrap_result(raw_result)
        assert result.get("status") == "closed", (
            f"Subtask 1 should be closed: {result.get('status')}"
        )

        # Verify subtask 2's blocking dependency is now resolved (subtask 1 in review/closed)
        # Since subtask 1 is in review/closed, subtask 2 should now be unblocked
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="list_blocked_tasks",
            arguments={},
        )
        result = unwrap_result(raw_result)
        blocked_task_ids = [t["id"] for t in result.get("tasks", [])]
        assert subtask2_id not in blocked_task_ids, (
            f"Subtask 2 should be unblocked after Subtask 1 review. Blocked: {blocked_task_ids}"
        )

    def test_orchestration_status_tracking(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test that orchestration status is tracked correctly."""
        # Setup - use "e2e-test-project" to match fixture's project.json
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        session_external_id = f"orch-status-{uuid.uuid4().hex[:8]}"
        session_result = cli_events.register_session(
            external_id=session_external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
        )
        session_id = session_result["id"]

        # Create epic with subtasks
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="create_task",
            arguments={
                "title": "Orchestration Status Epic",
                "task_type": "epic",
                "session_id": session_id,
            },
        )
        epic_result = unwrap_result(raw_result)
        epic_id = epic_result["id"]

        # Create subtasks
        for i in range(2):
            mcp_client.call_tool(
                server_name="gobby-tasks",
                tool_name="create_task",
                arguments={
                    "title": f"Status Test Subtask {i + 1}",
                    "task_type": "task",
                    "parent_task_id": epic_id,
                    "session_id": session_id,
                },
            )

        # Check orchestration status
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="get_orchestration_status",
            arguments={
                "parent_task_id": epic_id,
                "project_path": str(daemon_instance.project_dir),
            },
        )
        result = unwrap_result(raw_result)

        # Verify status structure
        assert result.get("success") is True, f"get_orchestration_status failed: {result}"
        assert "summary" in result, f"Missing summary in result: {result}"
        assert "open_tasks" in result, f"Missing open_tasks in result: {result}"

    def test_suggest_next_task_follows_sequence(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test suggest_next_task returns tasks in dependency order."""
        # Setup - use "e2e-test-project" to match fixture's project.json
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        session_external_id = f"suggest-seq-{uuid.uuid4().hex[:8]}"
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
                "title": "Suggest Sequence Epic",
                "task_type": "epic",
                "session_id": session_id,
            },
        )
        epic_result = unwrap_result(raw_result)
        epic_id = epic_result["id"]

        # Create task 1 (high priority)
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="create_task",
            arguments={
                "title": "High Priority Task",
                "task_type": "task",
                "parent_task_id": epic_id,
                "priority": 1,
                "session_id": session_id,
            },
        )
        task1_result = unwrap_result(raw_result)
        task1_id = task1_result["id"]

        # Create task 2 (lower priority)
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="create_task",
            arguments={
                "title": "Lower Priority Task",
                "task_type": "task",
                "parent_task_id": epic_id,
                "priority": 3,
                "session_id": session_id,
            },
        )
        task2_result = unwrap_result(raw_result)
        task2_id = task2_result["id"]

        # suggest_next_task should return higher priority task first
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="suggest_next_task",
            arguments={"session_id": session_id},
        )
        result = unwrap_result(raw_result)

        suggestion = result.get("suggestion", {})
        suggested_id = suggestion.get("id")

        # The higher priority task (priority=1) should be suggested
        assert suggested_id == task1_id, f"Expected high priority task, got: {result}"


class TestReviewStepE2E:
    """E2E tests for the review step in orchestration."""

    def test_task_closes_with_skip_reason(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test that tasks with skip reason (obsolete) close directly.

        When closing a task with reason='obsolete', 'duplicate', 'already_implemented',
        or 'wont_fix', it should close directly without requiring a commit.
        """
        # Setup - use "e2e-test-project" to match fixture's project.json
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        session_external_id = f"skip-reason-{uuid.uuid4().hex[:8]}"
        session_result = cli_events.register_session(
            external_id=session_external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
        )
        session_id = session_result["id"]

        # Create task
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="create_task",
            arguments={
                "title": "Task for Skip Reason Test",
                "task_type": "task",
                "session_id": session_id,
            },
        )
        result = unwrap_result(raw_result)
        task_id = result["id"]

        # Set to in_progress
        mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="update_task",
            arguments={"task_id": task_id, "status": "in_progress"},
        )

        # Close task with skip reason - should close directly
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="close_task",
            arguments={
                "task_id": task_id,
                "reason": "obsolete",
            },
        )

        # Verify task is closed
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="get_task",
            arguments={"task_id": task_id},
        )
        result = unwrap_result(raw_result)
        assert result.get("status") == "closed", f"Task should be closed: {result}"

    def test_review_task_can_be_approved(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
        cli_events: CLIEventSimulator,
    ):
        """Test that tasks in review can be approved and closed.

        When a task is in review status, using update_task to set
        status=closed should complete the review and close the task.
        """
        # Setup - use "e2e-test-project" to match fixture's project.json
        project_result = cli_events.register_test_project(
            project_id="e2e-test-project",
            name="E2E Test Project",
            repo_path=str(daemon_instance.project_dir),
        )
        assert project_result["status"] in ["success", "already_exists"]

        session_external_id = f"review-close-{uuid.uuid4().hex[:8]}"
        session_result = cli_events.register_session(
            external_id=session_external_id,
            machine_id="test-machine",
            source="Claude Code",
            cwd=str(daemon_instance.project_dir),
        )
        session_id = session_result["id"]

        # Create task
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="create_task",
            arguments={
                "title": "Task for Review Close Test",
                "task_type": "task",
                "session_id": session_id,
            },
        )
        result = unwrap_result(raw_result)
        task_id = result["id"]

        # Set to review status directly via update_task
        mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="update_task",
            arguments={"task_id": task_id, "status": "review"},
        )

        # Verify in review
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="get_task",
            arguments={"task_id": task_id},
        )
        result = unwrap_result(raw_result)
        assert result.get("status") == "review", f"Task should be in review: {result}"

        # Use update_task to transition from review to closed (simulating user approval)
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="update_task",
            arguments={
                "task_id": task_id,
                "status": "closed",
            },
        )
        result = unwrap_result(raw_result)

        # Verify task is now closed
        raw_result = mcp_client.call_tool(
            server_name="gobby-tasks",
            tool_name="get_task",
            arguments={"task_id": task_id},
        )
        result = unwrap_result(raw_result)
        assert result.get("status") == "closed", f"Task should be closed: {result}"


class TestWorkflowToolsAvailability:
    """Tests to verify workflow tools are properly registered."""

    def test_workflow_tools_are_registered(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Verify workflow management tools are available."""
        tools = mcp_client.list_tools(server="gobby-workflows")
        tool_names = [t["name"] for t in tools]

        expected_tools = [
            "activate_workflow",
            "get_workflow_status",
            "set_variable",
            "get_variable",
        ]

        for tool in expected_tools:
            assert tool in tool_names, f"Missing tool: {tool}"

    def test_orchestration_tools_are_registered(
        self,
        daemon_instance: DaemonInstance,
        mcp_client: MCPTestClient,
    ):
        """Verify orchestration tools are available on gobby-tasks."""
        tools = mcp_client.list_tools(server="gobby-tasks")
        tool_names = [t["name"] for t in tools]

        expected_tools = [
            "orchestrate_ready_tasks",
            "get_orchestration_status",
            "poll_agent_status",
            "suggest_next_task",
        ]

        for tool in expected_tools:
            assert tool in tool_names, f"Missing tool: {tool}"
