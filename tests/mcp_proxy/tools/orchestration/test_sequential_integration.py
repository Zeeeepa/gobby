"""Sequential orchestrator integration test.

Tests the meeseeks-box workflow end-to-end with mocked MCP calls,
verifying the full cycle: find_work → spawn_worker → wait_for_worker →
code_review → merge → cleanup → find_work (loop) → complete.

Uses real WorkflowEngine, ConditionEvaluator, ActionExecutor, and
WorkflowLoader with a mocked ToolProxyService to control MCP results.
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.hooks.events import HookEvent, HookEventType, SessionSource
from gobby.workflows.actions import ActionExecutor
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.engine import WorkflowEngine
from gobby.workflows.evaluator import ConditionEvaluator
from gobby.workflows.loader import _BUNDLED_WORKFLOWS_DIR, WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager
from gobby.workflows.templates import TemplateEngine

pytestmark = [pytest.mark.unit]

SESSION_ID = "orch-sess-1"


def _event(
    event_type: HookEventType = HookEventType.BEFORE_AGENT,
    data: dict | None = None,
) -> HookEvent:
    return HookEvent(
        event_type=event_type,
        session_id=SESSION_ID,
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data=data or {},
        metadata={"_platform_session_id": SESSION_ID},
    )


def _build_tool_proxy() -> AsyncMock:
    """Build a mock ToolProxyService that returns controlled MCP results."""
    proxy = AsyncMock()
    call_counts: dict[str, int] = {}

    async def mock_call_tool(
        server: str, tool: str, args: dict | None = None
    ) -> dict:
        key = f"{server}/{tool}"
        call_counts[key] = call_counts.get(key, 0) + 1
        count = call_counts[key]

        if tool == "suggest_next_task":
            if count == 1:
                return {"suggestion": {"ref": "#task-1"}}
            elif count == 2:
                return {"suggestion": {"ref": "#task-2"}}
            # Third call: no more tasks
            return {}

        if tool == "get_task":
            # Leaf task fallback — session_task itself is closed
            return {"status": "closed"}

        if tool == "spawn_agent":
            return {
                "run_id": f"worker-{count}",
                "clone_id": f"clone-{count}",
                "worktree_id": f"wt-{count}",
                "branch_name": f"branch-{count}",
            }

        if tool == "merge_clone_to_target":
            return {"success": True}

        if tool == "delete_clone":
            return {"success": True}

        return {}

    proxy.call_tool = mock_call_tool
    proxy._call_counts = call_counts
    return proxy


def _build_task_manager(tool_proxy: AsyncMock) -> MagicMock:
    """Build a mock task manager that tracks completion via tool_proxy call counts.

    Parent epic stays "open" until 3 suggest_next_task calls (all tasks exhausted),
    then switches to "closed" so task_tree_complete returns True.
    """
    tm = MagicMock()

    def mock_get_task(task_id: str) -> MagicMock:
        task = MagicMock()
        task.id = task_id
        task.requires_user_review = False
        if task_id == "#parent-epic":
            # Parent complete only after all suggest calls exhausted
            suggest_count = tool_proxy._call_counts.get(
                "gobby-tasks/suggest_next_task", 0
            )
            task.status = "closed" if suggest_count >= 3 else "open"
        else:
            task.status = "closed"
        return task

    tm.get_task = mock_get_task
    tm.get_subtasks = MagicMock(return_value=[])

    return tm


@pytest.fixture
def tool_proxy() -> AsyncMock:
    return _build_tool_proxy()


@pytest.fixture
def task_manager(tool_proxy) -> MagicMock:
    return _build_task_manager(tool_proxy)


@pytest.fixture
def state() -> WorkflowState:
    """Initial workflow state at find_work step."""
    return WorkflowState(
        session_id=SESSION_ID,
        workflow_name="meeseeks-box",
        step="find_work",
        step_entered_at=datetime.now(UTC),
        variables={
            "session_task": "#parent-epic",
            "isolation_mode": "clone",
            "worker_provider": "gemini",
            "worker_terminal": "tmux",
            "worker_timeout": 600,
            "max_wait_retries": 3,
            "wait_retry_count": 0,
            "max_review_attempts": 3,
            "review_attempt": 0,
            "review_approved": False,
            "review_deficiencies": [],
            "merge_target_branch": "dev",
        },
        context_injected=False,
    )


@pytest.fixture
def engine(tool_proxy, task_manager) -> tuple[WorkflowEngine, MagicMock]:
    """Build WorkflowEngine with real loader/evaluator, mocked MCP proxy."""
    # Use only bundled workflows dir — workflow_dirs must be non-empty ([] is falsy)
    # to avoid falling back to ~/.gobby/workflows/ which may have stale copies
    loader = WorkflowLoader(
        workflow_dirs=[Path("/tmp/gobby-test-no-workflows")],
        bundled_dir=_BUNDLED_WORKFLOWS_DIR,
    )
    state_manager = MagicMock(spec=WorkflowStateManager)
    template_engine = TemplateEngine()

    evaluator = ConditionEvaluator()
    evaluator.register_task_manager(task_manager)

    # Real ActionExecutor with mocked external deps
    action_executor = ActionExecutor(
        db=MagicMock(),
        session_manager=MagicMock(),
        template_engine=template_engine,
        tool_proxy_getter=lambda: tool_proxy,
    )
    # Session lookup returns None (not needed for this test)
    action_executor.session_manager.find_by_external_id.return_value = None

    engine = WorkflowEngine(
        loader=loader,
        state_manager=state_manager,
        action_executor=action_executor,
        evaluator=evaluator,
    )

    return engine, state_manager


class TestSequentialOrchestration:
    """Test meeseeks-box workflow processes 2 tasks sequentially."""

    @pytest.mark.asyncio
    async def test_full_sequential_cycle(
        self, engine, state, tool_proxy, task_manager
    ) -> None:
        """Drive the full workflow: 2 tasks through find→spawn→wait→review→merge→cleanup→complete."""
        wf_engine, state_manager = engine
        state_manager.get_state.return_value = state

        # --- Event 1: BEFORE_AGENT (initial entry) ---
        # Triggers on_enter for find_work: calls suggest_next_task, sets current_task_id
        # Auto-transitions: find_work → spawn_worker → wait_for_worker
        response = await wf_engine.handle_event(_event(HookEventType.BEFORE_AGENT))

        assert state.step == "wait_for_worker", f"Expected wait_for_worker, got {state.step}"
        assert state.variables.get("current_task_id") == "#task-1"
        assert state.variables.get("current_worker_id") == "worker-1"
        assert state.variables.get("current_clone_id") == "clone-1"
        assert response.decision == "modify"

        # --- Event 2: AFTER_TOOL with wait_for_task completed ---
        # Simulates the LLM calling wait_for_task and getting completed=true
        response = await wf_engine.handle_event(
            _event(
                HookEventType.AFTER_TOOL,
                data={
                    "tool_name": "mcp__gobby__call_tool",
                    "mcp_server": "gobby-orchestration",
                    "mcp_tool": "wait_for_task",
                    "tool_output": {"result": {"completed": True}},
                },
            )
        )

        assert state.step == "code_review", f"Expected code_review, got {state.step}"

        # --- Event 3: Set review_approved=true, send BEFORE_TOOL ---
        # Simulates the LLM approving the review
        state.variables["review_approved"] = True

        response = await wf_engine.handle_event(
            _event(
                HookEventType.BEFORE_TOOL,
                data={"tool_name": "Read"},
            )
        )

        # Should chain: code_review → merge → cleanup → find_work → spawn_worker → wait_for_worker
        assert state.step == "wait_for_worker", f"Expected wait_for_worker, got {state.step}"
        assert state.variables.get("current_task_id") == "#task-2"
        assert state.variables.get("current_worker_id") == "worker-2"

        # --- Event 4: AFTER_TOOL with wait_for_task completed (task 2) ---
        response = await wf_engine.handle_event(
            _event(
                HookEventType.AFTER_TOOL,
                data={
                    "tool_name": "mcp__gobby__call_tool",
                    "mcp_server": "gobby-orchestration",
                    "mcp_tool": "wait_for_task",
                    "tool_output": {"result": {"completed": True}},
                },
            )
        )

        assert state.step == "code_review", f"Expected code_review, got {state.step}"

        # --- Event 5: Approve review, task_tree_complete returns True ---
        state.variables["review_approved"] = True

        # task_tree_complete will return True automatically because
        # suggest_next_task count >= 3 by this point (fixture handles it)

        response = await wf_engine.handle_event(
            _event(
                HookEventType.BEFORE_TOOL,
                data={"tool_name": "Read"},
            )
        )

        # Should chain: code_review → merge → cleanup → find_work → complete
        assert state.step == "complete", f"Expected complete, got {state.step}"

        # Verify MCP calls were made in correct sequence
        counts = tool_proxy._call_counts
        assert counts.get("gobby-tasks/suggest_next_task", 0) == 3  # 2 tasks + 1 empty
        assert counts.get("gobby-agents/spawn_agent", 0) == 2
        assert counts.get("gobby-clones/merge_clone_to_target", 0) == 2
        assert counts.get("gobby-clones/delete_clone", 0) == 2

    @pytest.mark.asyncio
    async def test_wait_timeout_retries(self, engine, state, tool_proxy) -> None:
        """Wait timeout increments retry counter and stays in wait_for_worker."""
        wf_engine, state_manager = engine
        state_manager.get_state.return_value = state

        # Enter the workflow and reach wait_for_worker
        await wf_engine.handle_event(_event(HookEventType.BEFORE_AGENT))
        assert state.step == "wait_for_worker"

        # Send timeout result
        response = await wf_engine.handle_event(
            _event(
                HookEventType.AFTER_TOOL,
                data={
                    "tool_name": "mcp__gobby__call_tool",
                    "mcp_server": "gobby-orchestration",
                    "mcp_tool": "wait_for_task",
                    "tool_output": {"result": {"timed_out": True}},
                },
            )
        )

        # Should self-loop to wait_for_worker with incremented retry count
        assert state.step == "wait_for_worker"
        assert state.variables.get("wait_retry_count") == 1

    @pytest.mark.asyncio
    async def test_wait_max_retries_skips_to_cleanup(
        self, engine, state, tool_proxy, task_manager
    ) -> None:
        """Max wait retries exceeded skips to cleanup step."""
        wf_engine, state_manager = engine
        state_manager.get_state.return_value = state

        # Enter workflow and reach wait_for_worker
        await wf_engine.handle_event(_event(HookEventType.BEFORE_AGENT))
        assert state.step == "wait_for_worker"

        # Set retry count to max
        state.variables["wait_retry_count"] = 3
        state.variables["max_wait_retries"] = 3

        # Send timeout — should skip to cleanup since retries exhausted
        await wf_engine.handle_event(
            _event(
                HookEventType.AFTER_TOOL,
                data={
                    "tool_name": "mcp__gobby__call_tool",
                    "mcp_server": "gobby-orchestration",
                    "mcp_tool": "wait_for_task",
                    "tool_output": {"result": {"timed_out": True}},
                },
            )
        )

        # cleanup auto-transitions to find_work → spawn_worker → wait_for_worker
        # (since suggest_next_task returns task-2 on second call)
        assert state.step == "wait_for_worker", f"Expected wait_for_worker, got {state.step}"
        # Retry count should be reset by find_work on_enter
        assert state.variables.get("wait_retry_count") == 0

    @pytest.mark.asyncio
    async def test_dry_run_skips_spawn_to_complete(
        self, engine, state, tool_proxy
    ) -> None:
        """dry_run=true: find_work → spawn_worker → complete (no actual spawn)."""
        wf_engine, state_manager = engine
        state_manager.get_state.return_value = state

        # Enable dry_run
        state.variables["dry_run"] = True

        # Event 1: BEFORE_AGENT triggers find_work on_enter (suggest_next_task)
        # then transitions: find_work → spawn_worker → complete (dry_run shortcut)
        response = await wf_engine.handle_event(_event(HookEventType.BEFORE_AGENT))

        assert state.step == "complete", f"Expected complete, got {state.step}"
        assert state.variables.get("current_task_id") == "#task-1"

        # spawn_agent should NOT have been called (dry_run injects message instead)
        spawn_calls = tool_proxy._call_counts.get("gobby-agents/spawn_agent", 0)
        assert spawn_calls == 0, f"Expected 0 spawn_agent calls, got {spawn_calls}"
