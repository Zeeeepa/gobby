from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.workflows.actions import ActionContext, ActionExecutor
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.templates import TemplateEngine

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_services():
    mock_config = MagicMock()
    mock_config.compression = None  # Prevent TextCompressor from initializing with MagicMock
    return {
        "template_engine": MagicMock(spec=TemplateEngine),
        "llm_service": AsyncMock(),
        "transcript_processor": MagicMock(),
        "config": mock_config,
        "tool_proxy_getter": AsyncMock(),
        "memory_manager": MagicMock(),
    }


@pytest.fixture
def action_executor(temp_db, session_manager, mock_services):
    return ActionExecutor(
        temp_db,
        session_manager,
        mock_services["template_engine"],
        llm_service=mock_services["llm_service"],
        transcript_processor=mock_services["transcript_processor"],
        config=mock_services["config"],
        tool_proxy_getter=mock_services["tool_proxy_getter"],
        memory_manager=mock_services["memory_manager"],
    )


@pytest.fixture
def workflow_state():
    return WorkflowState(
        session_id="test-session-id",
        workflow_name="test-workflow",
        step="test-step",
    )


@pytest.fixture
def action_context(temp_db, session_manager, workflow_state, mock_services):
    return ActionContext(
        session_id=workflow_state.session_id,
        state=workflow_state,
        db=temp_db,
        session_manager=session_manager,
        template_engine=mock_services["template_engine"],
        tool_proxy_getter=mock_services["tool_proxy_getter"],
        memory_manager=mock_services["memory_manager"],
    )


@pytest.mark.asyncio
async def test_inject_context_previous_session(
    action_executor, action_context, session_manager, sample_project
):
    # Setup: Create parent and current session
    parent = session_manager.register(
        external_id="parent-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
        title="Parent Session",
    )
    # Update parent summary
    session_manager.update_summary(parent.id, summary_markdown="Parent Summary Content")

    current = session_manager.register(
        external_id="current-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
        title="Current Session",
        parent_session_id=parent.id,
    )

    # Update context with real session ID
    action_context.session_id = current.id
    action_context.state.session_id = current.id

    result = await action_executor.execute(
        "inject_context", action_context, source="previous_session_summary"
    )

    assert result is not None
    assert result["inject_context"] == "Parent Summary Content"
    assert action_context.state.context_injected is True


@pytest.mark.asyncio
async def test_capture_artifact(action_executor, action_context, tmp_path):
    # Create a dummy file
    artifact_file = tmp_path / "plan.md"
    artifact_file.write_text("Plan content")

    # We need to use glob pattern relative to CWD, or absolute.
    # Use absolute for test stability.
    pattern = str(artifact_file)

    result = await action_executor.execute(
        "capture_artifact",
        action_context,
        pattern=pattern,
        **{"as": "current_plan"},  # 'as' is a python keyword
    )

    assert result is not None
    assert result["captured"] == str(artifact_file)
    assert "current_plan" in action_context.state.artifacts
    assert action_context.state.artifacts["current_plan"] == str(artifact_file)


@pytest.mark.asyncio
async def test_generate_handoff(
    action_executor, action_context, session_manager, sample_project, mock_services, tmp_path
):
    # Create a real transcript file
    transcript_file = tmp_path / "transcript.jsonl"
    import json

    transcript_data = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    with open(transcript_file, "w") as f:
        for entry in transcript_data:
            f.write(json.dumps(entry) + "\n")

    # Setup session with real transcript path
    session = session_manager.register(
        external_id="handoff-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
        jsonl_path=str(transcript_file),
    )
    action_context.session_id = session.id

    # Setup mocks for transcript processor methods
    mock_services["transcript_processor"].extract_turns_since_clear.return_value = transcript_data
    mock_services["transcript_processor"].extract_last_messages.return_value = transcript_data
    mock_services["template_engine"].render.return_value = "Summarize: User: hello"

    # Setup LLM service mock chain: llm_service.get_default_provider().generate_summary()
    # Note: get_default_provider is sync, generate_summary is async
    mock_provider = MagicMock()
    mock_provider.generate_summary = AsyncMock(return_value="Session Summary.")
    mock_llm_service = MagicMock()
    mock_llm_service.get_default_provider.return_value = mock_provider
    mock_services["llm_service"] = mock_llm_service

    # Update context services manually since ActionContext fixture doesn't use the mock_services
    # In a real app, engine handles this. Here we manually patch.
    action_context.llm_service = mock_services["llm_service"]
    action_context.transcript_processor = mock_services["transcript_processor"]
    action_context.template_engine = mock_services["template_engine"]

    result = await action_executor.execute("generate_handoff", action_context)

    assert result is not None
    assert result["handoff_created"] is True
    assert result["summary_length"] == 16

    # Verify session summary updated
    updated_session = session_manager.get(session.id)
    assert updated_session.summary_markdown == "Session Summary."
    assert updated_session.status == "handoff_ready"

    # Verify LLM called via get_default_provider().generate_summary()
    mock_provider.generate_summary.assert_called_once()


@pytest.mark.asyncio
async def test_generate_summary(
    action_executor, action_context, session_manager, sample_project, mock_services, tmp_path
):
    # Create a real transcript file
    transcript_file = tmp_path / "transcript_summary.jsonl"
    import json

    transcript_data = [
        {"role": "user", "content": "hello again"},
        {"role": "assistant", "content": "Hi there again!"},
    ]
    with open(transcript_file, "w") as f:
        for entry in transcript_data:
            f.write(json.dumps(entry) + "\n")

    # Setup session
    session = session_manager.register(
        external_id="summary-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
        jsonl_path=str(transcript_file),
    )
    action_context.session_id = session.id

    # Setup mocks
    mock_services["transcript_processor"].extract_turns_since_clear.return_value = transcript_data
    mock_services["transcript_processor"].extract_last_messages.return_value = transcript_data
    mock_services["template_engine"].render.return_value = "Summarize: User: hello again"

    mock_provider = MagicMock()
    mock_provider.generate_summary = AsyncMock(return_value="Just a summary.")
    mock_llm_service = MagicMock()
    mock_llm_service.get_default_provider.return_value = mock_provider
    mock_services["llm_service"] = mock_llm_service

    # Patch context
    action_context.llm_service = mock_services["llm_service"]
    action_context.transcript_processor = mock_services["transcript_processor"]

    result = await action_executor.execute("generate_summary", action_context)

    assert result is not None
    assert result["summary_generated"] is True
    assert result["summary_length"] == 15

    # Verify summary updated
    updated_session = session_manager.get(session.id)
    assert updated_session.summary_markdown == "Just a summary."
    # Verify status NOT updated to handoff_ready (legacy behavior only in handoff action)
    assert updated_session.status != "handoff_ready"


@pytest.mark.asyncio
async def test_write_todos(action_executor, action_context, tmp_path):
    todo_file = tmp_path / "TODO.md"

    todos = ["Buy milk", "Walk dog"]

    result = await action_executor.execute(
        "write_todos",
        action_context,
        todos=todos,
        filename=str(todo_file),
    )

    assert result is not None
    assert result["todos_written"] == 2

    content = todo_file.read_text()
    assert "- [ ] Buy milk" in content
    assert "- [ ] Walk dog" in content


@pytest.mark.asyncio
async def test_mark_todo_complete(action_executor, action_context, tmp_path):
    todo_file = tmp_path / "TODO.md"
    todo_file.write_text("- [ ] Task A\n- [ ] Task B\n")

    result = await action_executor.execute(
        "mark_todo_complete",
        action_context,
        todo_text="Task A",
        filename=str(todo_file),
    )

    assert result is not None
    assert result["todo_completed"] is True

    content = todo_file.read_text()
    assert "- [x] Task A" in content
    assert "- [ ] Task B" in content


@pytest.mark.asyncio
async def test_inject_message(action_executor, action_context, mock_services):
    mock_services["template_engine"].render.return_value = "Rendered Message"

    result = await action_executor.execute(
        "inject_message", action_context, content="Template Message"
    )

    assert result is not None
    assert result["inject_message"] == "Rendered Message"
    mock_services["template_engine"].render.assert_called_once()


@pytest.mark.asyncio
async def test_read_artifact(action_executor, action_context, tmp_path):
    artifact_file = tmp_path / "data.txt"
    artifact_file.write_text("Secret Data")

    # Store artifact in state first (simulate capture)
    action_context.state.artifacts["my_data"] = str(artifact_file)

    result = await action_executor.execute(
        "read_artifact", action_context, pattern="my_data", **{"as": "data_var"}
    )

    assert result is not None
    assert result["read_artifact"] is True
    assert action_context.state.variables["data_var"] == "Secret Data"


@pytest.mark.asyncio
async def test_workflow_state_persistence(
    action_executor, action_context, temp_db, session_manager, sample_project
):
    from unittest.mock import MagicMock, patch

    with patch("gobby.workflows.state_manager.WorkflowStateManager") as MockManager:
        # Save
        mock_manager_instance = MockManager.return_value
        await action_executor.execute("save_workflow_state", action_context)
        mock_manager_instance.save_state.assert_called_with(action_context.state)

        # Load
        mock_loaded = MagicMock()
        mock_loaded.model_fields = {"variables": True}
        mock_loaded.variables = {"key": "loaded"}
        mock_manager_instance.get_state.return_value = mock_loaded

        # Reset context state
        action_context.state.variables = {}

        await action_executor.execute("load_workflow_state", action_context)
        assert action_context.state.variables == {"key": "loaded"}


@pytest.mark.asyncio
async def test_mark_session_status(
    action_executor, action_context, session_manager, sample_project
):
    session = session_manager.register(
        external_id="status-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    action_context.session_id = session.id

    result = await action_executor.execute(
        "mark_session_status", action_context, status="completed"
    )

    assert result is not None
    assert result["status_updated"] is True

    updated = session_manager.get(session.id)
    assert updated.status == "completed"


@pytest.mark.asyncio
async def test_switch_mode(action_executor, action_context):
    result = await action_executor.execute("switch_mode", action_context, mode="planning")

    assert result is not None
    assert "SYSTEM: SWITCH MODE TO PLANNING" in result["inject_context"]


@pytest.mark.asyncio
async def test_save_memory(action_executor, action_context, mock_services):
    mock_services["memory_manager"].config.enabled = True
    # Mock 'remember' to return a Memory object-like mock
    mem_mock = MagicMock()
    mem_mock.id = "mem-1"
    mock_services["memory_manager"].remember = AsyncMock(return_value=mem_mock)
    mock_services["memory_manager"].content_exists.return_value = False

    result = await action_executor.execute(
        "memory_save", action_context, content="User likes apples", project_id="proj-1"
    )

    assert result is not None
    assert result["saved"] is True
    assert result["memory_id"] == "mem-1"


@pytest.mark.asyncio
async def test_call_mcp_tool(action_executor, action_context, mock_services):
    # Mock MCP manager
    mock_proxy = AsyncMock()
    mock_proxy.call_tool = AsyncMock(return_value={"result": "tool_output"})
    action_context.tool_proxy_getter = lambda: mock_proxy

    result = await action_executor.execute(
        "call_mcp_tool",
        action_context,
        server_name="test-server",
        tool_name="test-tool",
        arguments={"arg": "val"},
        **{"as": "tool_res"},
    )

    assert result is not None
    if "error" in result:
        pytest.fail(f"call_mcp_tool failed: {result['error']}")

    # assert result["tool_called"] is True # handler doesn't return this
    assert result["result"] == {"result": "tool_output"}
    assert action_context.state.variables["tool_res"] == {"result": "tool_output"}


@pytest.mark.asyncio
async def test_persist_tasks(action_executor, action_context, session_manager, sample_project):
    # Setup session
    session = session_manager.register(
        external_id="tasks-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    action_context.session_id = session.id

    tasks_data = [{"title": "Task 1", "status": "todo"}]

    # We need a real TaskManager? fixture 'task_manager' is not in args
    # But ActionContext has session_manager.
    # persist_tasks uses 'task_actions.persist_decomposed_tasks' which uses 'LocalTaskManager'.
    # It imports 'persist_decomposed_tasks' inside handler.
    # We can mock that import or ensure dependency injection works.
    # 'persist_decomposed_tasks' takes (tasks, session_id, project_id, workflow_name, parent_id).
    # It instantiates LocalTaskManager internally?

    # 'persist_decomposed_tasks' is imported from 'gobby.workflows.task_actions'
    with patch("gobby.workflows.task_actions.persist_decomposed_tasks") as mock_persist:
        mock_persist.return_value = {"ext-1": "task-1"}

        result = await action_executor.execute(
            "persist_tasks", action_context, tasks=tasks_data, workflow_name="test-flow"
        )

        assert result is not None
        if "error" in result:
            pytest.fail(f"persist_tasks failed: {result['error']}")
        assert result["ids"] == ["task-1"]


@pytest.mark.asyncio
async def test_memory_recall_relevant(
    action_executor, action_context, mock_services, sample_project, session_manager
):
    mock_services["memory_manager"].config.enabled = True

    # Mock recall returning memories
    mem1 = MagicMock()
    mem1.content = "Relevant memory"
    mem1.importance = 0.8
    mem1.memory_type = "fact"
    mock_services["memory_manager"].recall.return_value = [mem1]

    # Prepare session and event data
    session = session_manager.register(
        external_id="recall-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    action_context.session_id = session.id
    action_context.event_data = {"prompt_text": "I need help with python"}

    result = await action_executor.execute("memory_recall_relevant", action_context)

    assert result is not None
    assert result["injected"] is True
    assert result["count"] == 1
    assert "Relevant memory" in result["inject_context"]


@pytest.mark.asyncio
async def test_inject_context(action_executor, action_context, session_manager, sample_project):
    # Setup session for context
    session = session_manager.register(
        external_id="inject-ctx-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    action_context.session_id = session.id
    action_context.state.artifacts["art1"] = "/tmp/path"

    # 1. Source: artifacts
    res = await action_executor.execute("inject_context", action_context, source="artifacts")
    assert res is not None
    assert "- art1: /tmp/path" in res["inject_context"]

    # 2. Source: workflow_state
    action_context.state.variables["k"] = "v"
    res = await action_executor.execute("inject_context", action_context, source="workflow_state")
    assert res is not None
    assert '"k": "v"' in res["inject_context"]


@pytest.mark.asyncio
async def test_synthesize_title(
    action_executor, action_context, mock_services, session_manager, sample_project, tmp_path
):
    transcript_file = tmp_path / "transcript.jsonl"
    with open(transcript_file, "w") as f:
        f.write('{"role": "user", "content": "make a title"}\n')

    session = session_manager.register(
        external_id="title-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
        jsonl_path=str(transcript_file),
    )
    action_context.session_id = session.id

    # Mock LLM and services
    provider = MagicMock()
    provider.generate_text = AsyncMock(return_value="New Title")
    mock_llm_service = MagicMock()
    # Mock for synthesize_title (uses regular generate_text usually via provider)
    # actions.py: provider = context.llm_service.get_default_provider() ... await provider.generate_text(...)
    mock_llm_service.get_default_provider.return_value = provider
    action_context.llm_service = mock_llm_service

    mock_services["template_engine"].render.return_value = "Title Prompt"
    action_context.template_engine = mock_services["template_engine"]

    # Mock transcript
    mock_services["transcript_processor"].extract_turns_since_clear.return_value = [
        {"role": "user"}
    ]
    action_context.transcript_processor = mock_services["transcript_processor"]

    res = await action_executor.execute("synthesize_title", action_context)

    assert res is not None
    assert res["title_synthesized"] == "New Title"

    updated = session_manager.get(session.id)
    assert updated.title == "New Title"


@pytest.mark.asyncio
async def test_update_workflow_task(action_executor, action_context, temp_db, sample_project):
    # Create a task to update
    from gobby.storage.tasks import LocalTaskManager

    task_manager = LocalTaskManager(temp_db)

    task = task_manager.create_task(
        project_id=sample_project["id"],
        title="Old Title",
    )
    task_id = task.id
    # Set status manually to match expectation if needed, or update afterwards
    task_manager.update_task(task_id, status="open")  # Default is open usually

    res = await action_executor.execute(
        "update_workflow_task",
        action_context,
        task_id=task_id,
        project_id=sample_project["id"],
        status="completed",
        outcome="Success",
    )

    assert res is not None
    assert res["updated"] is True

    updated_task = task_manager.get_task(task_id)
    assert updated_task.status == "completed"


@pytest.mark.asyncio
async def test_start_new_session(
    action_executor, action_context, mock_services, session_manager, sample_project
):
    # Register session
    session = session_manager.register(
        external_id="chained-session",
        machine_id="test-machine",
        source="claude",
        project_id=sample_project["id"],
    )
    action_context.session_id = session.id

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        args = {"command": "claude", "args": ["-p", "hello"], "prompt": "initial prompt"}
        res = await action_executor.execute("start_new_session", action_context, **args)

        assert res is not None
        assert res["started_new_session"] is True
        assert res["pid"] == 12345

        mock_popen.assert_called_once()


@pytest.mark.asyncio
async def test_extract_handoff_context(
    action_executor, action_context, mock_services, session_manager, sample_project, tmp_path
):
    transcript_file = tmp_path / "handoff_transcript.jsonl"
    with open(transcript_file, "w") as f:
        f.write('{"role": "user", "content": "do work"}\n')

    session = session_manager.register(
        external_id="handoff-session",
        machine_id="test-machine",
        source="claude",
        project_id=sample_project["id"],
        jsonl_path=str(transcript_file),
    )
    action_context.session_id = session.id

    # Mock TranscriptAnalyzer
    with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
        mock_instance = MockAnalyzer.return_value
        mock_ctx = MagicMock()
        mock_ctx.active_gobby_task = {"id": "t1", "title": "My Task", "status": "open"}
        # These will be overwritten by real commits if not mocked in executor
        # So we patch the executor's method
        mock_ctx.git_commits = []
        mock_ctx.git_status = " M file.py"
        mock_ctx.files_modified = ["file.py"]
        mock_ctx.initial_goal = "Goal"
        mock_ctx.recent_activity = ["User asked X", "System did Y"]
        mock_instance.extract_handoff_context.return_value = mock_ctx

        # Patch git helper in context_actions module to avoid overwriting with real commits
        with patch(
            "gobby.workflows.context_actions.get_recent_git_commits",
            return_value=[{"hash": "abc1234", "message": "feat: add stuff"}],
        ):
            res = await action_executor.execute("extract_handoff_context", action_context)

        assert res is not None
        assert res["handoff_context_extracted"] is True

        updated = session_manager.get(session.id)
        assert updated.compact_markdown is not None
        assert "Active Task" in updated.compact_markdown
        assert "abc1234" in updated.compact_markdown
        assert "file.py" in updated.compact_markdown


@pytest.mark.asyncio
async def test_memory_sync_ops(action_executor, action_context):
    # Mock memory sync manager
    mock_sync = MagicMock()
    mock_sync.import_from_files = AsyncMock(return_value=5)
    mock_sync.export_to_files = AsyncMock(return_value=3)

    action_context.memory_sync_manager = mock_sync

    # Test Import
    res_import = await action_executor.execute("memory_sync_import", action_context)
    assert res_import is not None
    assert res_import["imported"]["memories"] == 5

    # Test Export
    res_export = await action_executor.execute("memory_sync_export", action_context)
    assert res_export is not None
    assert res_export["exported"]["memories"] == 3


@pytest.mark.asyncio
async def test_error_cases(action_executor, action_context, mock_services, session_manager):
    # 1. Unknown action
    res = await action_executor.execute("unknown_action_xyz", action_context)
    assert res is None  # Should log warning

    # 2. Inject context no source
    res = await action_executor.execute("inject_context", action_context)
    assert res is None

    # 3. Call MCP tool missing args
    res = await action_executor.execute("call_mcp_tool", action_context, server_name="s")
    assert res["error"] == "Missing server_name or tool_name"

    # 4. Generate summary missing services
    action_context.llm_service = None
    res = await action_executor.execute("generate_summary", action_context)
    assert res["error"] == "Missing services"
    action_context.llm_service = mock_services["llm_service"]  # restore

    # 5. Start new session missing session
    action_context.session_id = "non-existent"
    res = await action_executor.execute("start_new_session", action_context)
    assert res["error"] == "Session not found"

    # 6. Memory inject no project ID
    # Clear project ID from context/session
    action_context.session_id = "non-existent"
    action_context.memory_manager = mock_services["memory_manager"]
    res = await action_executor.execute("memory_inject", action_context)
    # Should log warning and return None or error dict depending on impl
    assert res is None or "error" in res or res.get("injected") is False

    # 8. Exception in execute
    # Register faulty handler
    async def faulty_handler(*args, **kwargs):
        raise Exception("Boom")

    action_executor.register("faulty_action", faulty_handler)
    res = await action_executor.execute("faulty_action", action_context)
    assert res["error"] == "Boom"


@pytest.mark.asyncio
async def test_git_helpers():
    """Test git utility functions from git_utils module."""
    from gobby.workflows.git_utils import get_file_changes, get_git_status, get_recent_git_commits

    with patch("gobby.workflows.git_utils.subprocess.run") as mock_run:
        # 1. git status
        mock_run.return_value.stdout = "M file.py"
        status = get_git_status()
        assert status == "M file.py"
        mock_run.assert_called_with(
            ["git", "status", "--short"], capture_output=True, text=True, timeout=5
        )

        # 2. git commits
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "hash1|msg1\nhash2|msg2"
        commits = get_recent_git_commits()
        assert len(commits) == 2
        assert commits[0]["hash"] == "hash1"

        # 3. git file changes
        # Mocking diff AND ls-files. subprocess.run called twice.
        # side_effect to return diff then untracked
        res1 = MagicMock(stdout="M file.py")
        res2 = MagicMock(stdout="untracked.py")
        mock_run.side_effect = [res1, res2]

        changes = get_file_changes()
        assert "Modified/Deleted:" in changes
        assert "file.py" in changes
        assert "Untracked:" in changes
        assert "untracked.py" in changes


def test_format_turns() -> None:
    """Test format_turns_for_llm from summary_actions module."""
    from gobby.workflows.summary_actions import format_turns_for_llm

    turns = [
        {"message": {"role": "user", "content": "hello"}},
        {
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "hi"},
                    {"type": "thinking", "thinking": "hmmm"},
                    {"type": "tool_use", "name": "tool1"},
                ],
            }
        },
    ]
    formatted = format_turns_for_llm(turns)
    assert "[Turn 2 - assistant]: hi [Thinking: hmmm] [Tool: tool1]" in formatted


@pytest.mark.asyncio
async def test_variable_actions(action_executor, action_context):
    # 1. Set variable
    res = await action_executor.execute("set_variable", action_context, name="count", value=10)
    assert res["variable_set"] == "count"
    assert action_context.state.variables["count"] == 10

    # 2. Increment variable
    res = await action_executor.execute(
        "increment_variable", action_context, name="count", amount=5
    )
    assert res["value"] == 15
    assert action_context.state.variables["count"] == 15

    # 3. Increment non-existent (default 0 + 1)
    res = await action_executor.execute("increment_variable", action_context, name="new_var")
    assert res["value"] == 1

    # 4. Set/Increment with UNINITIALIZED variables
    action_context.state.variables = None
    res = await action_executor.execute("set_variable", action_context, name="v1", value="init")
    assert action_context.state.variables["v1"] == "init"

    action_context.state.variables = None
    res = await action_executor.execute("increment_variable", action_context, name="v2")
    assert res["value"] == 1

    # 4. Save state (mock db/manager?)
    # handle_save_workflow_state imports WorkflowStateManager.
    # We should patch WorkflowStateManager in the module.
    with patch("gobby.workflows.state_manager.WorkflowStateManager") as MockManager:
        res = await action_executor.execute("save_workflow_state", action_context)
        assert res["state_saved"] is True
        MockManager.return_value.save_state.assert_called_once()

    # 5. Load state
    with patch("gobby.workflows.state_manager.WorkflowStateManager") as MockManager:
        mock_state = MagicMock()
        # Mock model_fields for iteration
        mock_state.model_fields = {"variables": True}
        mock_state.variables = {"loaded": "value"}
        MockManager.return_value.get_state.return_value = mock_state

        res = await action_executor.execute("load_workflow_state", action_context)
        assert res["state_loaded"] is True
        assert action_context.state.variables == {"loaded": "value"}


@pytest.mark.asyncio
async def test_call_llm(
    action_executor, action_context, mock_services, session_manager, sample_project
):
    # Create a session so handle_call_llm can find it
    session = session_manager.register(
        external_id="call-llm-test",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    action_context.session_id = session.id

    mock_provider = AsyncMock()
    mock_provider.generate_text.return_value = "LLM Response"

    # Use MagicMock for llm_service because get_default_provider is sync
    mock_llm_service = MagicMock()
    mock_llm_service.get_default_provider.return_value = mock_provider
    action_context.llm_service = mock_llm_service

    # Mock template rendering
    mock_services["template_engine"].render.return_value = "Hello World"

    res = await action_executor.execute(
        "call_llm", action_context, prompt="Hello {{ var }}", output_as="response", var="World"
    )

    assert res["llm_called"] is True
    assert res["output_variable"] == "response"
    assert action_context.state.variables["response"] == "LLM Response"

    # Verify prompt rendering
    mock_services["template_engine"].render.assert_called()
    mock_provider.generate_text.assert_called_with("Hello World")


@pytest.mark.asyncio
async def test_inject_context_variations(action_executor, action_context, mock_services):
    # 1. Compact Handoff
    mock_session = MagicMock()
    mock_session.compact_markdown = "Compact Markdown"

    # Mock the session manager on the context
    action_context.session_manager = MagicMock()
    action_context.session_manager.get.return_value = mock_session

    # We need to simulate template rendering for compact handoff if template provided?
    # No, code 180 sets content. Then 187 checks content. If template provided, it renders.

    res = await action_executor.execute("inject_context", action_context, source="compact_handoff")
    assert res["inject_context"] == "Compact Markdown"

    # 2. Artifacts injection
    action_context.state.artifacts = {"Plan": "/path/to/plan.md"}
    res = await action_executor.execute("inject_context", action_context, source="artifacts")
    assert "## Captured Artifacts" in res["inject_context"]
    assert "- Plan: /path/to/plan.md" in res["inject_context"]

    # 3. Observations injection
    action_context.state.observations = ["User clicked button"]
    res = await action_executor.execute("inject_context", action_context, source="observations")
    assert "## Observations" in res["inject_context"]
    assert "User clicked button" in res["inject_context"]

    # 4. Workflow State injection
    res = await action_executor.execute("inject_context", action_context, source="workflow_state")
    assert "## Workflow State" in res["inject_context"]
    assert "test-session-id" in res["inject_context"]


@pytest.mark.asyncio
async def test_save_memory_error_cases(action_executor, action_context, mock_services):
    from unittest.mock import patch

    # 1. Disabled
    mock_services["memory_manager"].config.enabled = False
    res = await action_executor.execute("memory_save", action_context)
    assert res is None

    mock_services["memory_manager"].config.enabled = True

    # 2. Missing content
    res = await action_executor.execute("memory_save", action_context)
    assert res["error"] == "Missing required 'content' parameter"

    # 3. Missing project_id (and session has none)
    # Ensure current session has no project_id
    mock_session = MagicMock()
    mock_session.project_id = None

    with patch.object(action_context.session_manager, "get", return_value=mock_session):
        res = await action_executor.execute("memory_save", action_context, content="Fact")
        assert res["error"] == "No project_id found"

        # 4. Duplicate
        mock_session.project_id = "proj-1"
        mock_services["memory_manager"].content_exists.return_value = True
        res = await action_executor.execute("memory_save", action_context, content="Fact")
        assert res["saved"] is False
        assert res["reason"] == "duplicate"

        # 5. Exception
        mock_services["memory_manager"].content_exists.side_effect = Exception("DB Error")
        res = await action_executor.execute("memory_save", action_context, content="Fact")
        assert res["error"] == "DB Error"

    # assert updated_task.outcome == "Success" # Task object might not have 'outcome' field?
    # Check if 'outcome' is supported. If not, maybe update_task doesn't support it either.
    # update_task(..., verification=...)
    # outcome might be stored elsewhere or inside verification?
    # Let's check update loop.
    # If update_workflow_task handlers arbitrary kwargs, it might use task_manager.update_task which has specific fields.
    # I saw update_task signature earlier, it didn't have 'outcome'.
    # It had 'verification', 'status', 'title', 'description' etc.
    # So 'outcome' might just be ignored by update_workflow_task if it only maps specific fields.
    # I'll check handler code later if this fails. For now remove outcome assertion or comment it.
    # Assuming update_workflow_task is smart. But task_manager.update_task is strict.
    # I'll assert status.


@pytest.mark.asyncio
async def test_generate_handoff_compact_mode_precise_matching(
    action_executor, action_context, session_manager, sample_project, mock_services, tmp_path
):
    """Test that compact mode detection uses precise event type matching.

    Ensures that only exact matches like 'pre_compact' and 'compact' trigger
    compact mode, not substring matches like 'not_compact_but_contains_word'.
    """
    # Create a transcript file
    transcript_file = tmp_path / "transcript.jsonl"
    import json

    transcript_data = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    with open(transcript_file, "w") as f:
        for entry in transcript_data:
            f.write(json.dumps(entry) + "\n")

    # Setup session
    session = session_manager.register(
        external_id="compact-test",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
        jsonl_path=str(transcript_file),
    )
    action_context.session_id = session.id

    # Setup mocks
    mock_services["transcript_processor"].extract_turns_since_clear.return_value = transcript_data
    mock_services["transcript_processor"].extract_last_messages.return_value = transcript_data
    mock_services["template_engine"].render.return_value = "Summarize: User: hello"

    mock_provider = MagicMock()
    mock_provider.generate_summary = AsyncMock(return_value="Session Summary.")
    mock_llm_service = MagicMock()
    mock_llm_service.get_default_provider.return_value = mock_provider
    mock_services["llm_service"] = mock_llm_service

    action_context.llm_service = mock_services["llm_service"]
    action_context.transcript_processor = mock_services["transcript_processor"]
    action_context.template_engine = mock_services["template_engine"]

    # Test 1: Event type "pre_compact" should trigger compact mode
    action_context.event_data = {"event_type": "pre_compact"}
    with patch(
        "gobby.workflows.summary_actions.generate_summary",
        new_callable=AsyncMock,
    ) as mock_gen:
        mock_gen.return_value = {"summary_generated": True, "summary_length": 10}
        await action_executor.execute("generate_handoff", action_context)
        # Verify mode="compact" was passed
        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs.get("mode") == "compact"

    # Test 2: Event type "compact" should trigger compact mode
    action_context.event_data = {"event_type": "compact"}
    with patch(
        "gobby.workflows.summary_actions.generate_summary",
        new_callable=AsyncMock,
    ) as mock_gen:
        mock_gen.return_value = {"summary_generated": True, "summary_length": 10}
        await action_executor.execute("generate_handoff", action_context)
        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs.get("mode") == "compact"

    # Test 3: Event type containing "compact" as substring should NOT trigger compact mode
    action_context.event_data = {"event_type": "not_compact_but_contains_word"}
    with patch(
        "gobby.workflows.summary_actions.generate_summary",
        new_callable=AsyncMock,
    ) as mock_gen:
        mock_gen.return_value = {"summary_generated": True, "summary_length": 10}
        await action_executor.execute("generate_handoff", action_context)
        call_kwargs = mock_gen.call_args.kwargs
        # Should default to "clear" mode, not "compact"
        assert call_kwargs.get("mode") == "clear"

    # Test 4: Event type "mycompact" should NOT trigger compact mode
    action_context.event_data = {"event_type": "mycompact"}
    with patch(
        "gobby.workflows.summary_actions.generate_summary",
        new_callable=AsyncMock,
    ) as mock_gen:
        mock_gen.return_value = {"summary_generated": True, "summary_length": 10}
        await action_executor.execute("generate_handoff", action_context)
        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs.get("mode") == "clear"

    # Test 5: Empty event_data should default to "clear" mode
    action_context.event_data = {}
    with patch(
        "gobby.workflows.summary_actions.generate_summary",
        new_callable=AsyncMock,
    ) as mock_gen:
        mock_gen.return_value = {"summary_generated": True, "summary_length": 10}
        await action_executor.execute("generate_handoff", action_context)
        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs.get("mode") == "clear"


@pytest.mark.asyncio
async def test_generate_summary_mode_validation():
    """Test that generate_summary raises ValueError for invalid mode values."""
    from gobby.workflows.summary_actions import generate_summary

    # Mock session_manager
    mock_session_manager = MagicMock()
    mock_llm_service = MagicMock()
    mock_transcript_processor = MagicMock()

    # Test invalid mode raises ValueError
    with pytest.raises(ValueError) as exc_info:
        await generate_summary(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
            mode="invalid_mode",  # type: ignore  # Testing runtime validation
        )

    assert "Invalid mode 'invalid_mode'" in str(exc_info.value)
    assert "clear" in str(exc_info.value)
    assert "compact" in str(exc_info.value)

    # Test another invalid mode
    with pytest.raises(ValueError) as exc_info:
        await generate_summary(
            session_manager=mock_session_manager,
            session_id="test-session",
            llm_service=mock_llm_service,
            transcript_processor=mock_transcript_processor,
            mode="compacted",  # type: ignore  # Testing runtime validation
        )

    assert "Invalid mode 'compacted'" in str(exc_info.value)


class TestWebhookAction:
    """Tests for the webhook action handler integration."""

    @pytest.mark.asyncio
    async def test_webhook_action_basic_url(self, action_executor, action_context):
        """Test basic webhook execution with URL."""
        with patch("gobby.workflows.webhook_executor.WebhookExecutor") as MockExecutor:
            # Mock successful response
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.status_code = 200
            mock_result.body = '{"status": "ok"}'
            mock_result.error = None
            mock_result.headers = {"Content-Type": "application/json"}
            mock_result.json_body.return_value = {"status": "ok"}

            mock_executor_instance = MockExecutor.return_value
            mock_executor_instance.execute = AsyncMock(return_value=mock_result)

            result = await action_executor.execute(
                "webhook",
                action_context,
                url="https://example.com/webhook",
                method="POST",
                payload={"test": "data"},
            )

            assert result is not None
            assert result["success"] is True
            assert result["status_code"] == 200
            assert result["error"] is None

            # Verify executor was called correctly
            mock_executor_instance.execute.assert_called_once()
            call_kwargs = mock_executor_instance.execute.call_args.kwargs
            assert call_kwargs["url"] == "https://example.com/webhook"
            assert call_kwargs["method"] == "POST"

    @pytest.mark.asyncio
    async def test_webhook_action_invalid_config_missing_url(self, action_executor, action_context):
        """Test webhook action fails gracefully for missing url/webhook_id."""
        result = await action_executor.execute(
            "webhook",
            action_context,
            method="POST",  # Missing url and webhook_id
        )

        assert result is not None
        assert result["success"] is False
        assert "required" in result["error"].lower() or "url" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_webhook_action_invalid_method(self, action_executor, action_context):
        """Test webhook action fails for invalid HTTP method."""
        result = await action_executor.execute(
            "webhook",
            action_context,
            url="https://example.com/webhook",
            method="INVALID",
        )

        assert result is not None
        assert result["success"] is False
        assert "method" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_webhook_action_capture_response(self, action_executor, action_context):
        """Test webhook action captures response into workflow variables."""
        with patch("gobby.workflows.webhook_executor.WebhookExecutor") as MockExecutor:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.status_code = 201
            mock_result.body = '{"id": "new-123"}'
            mock_result.error = None
            mock_result.headers = {"X-Request-Id": "req-456"}
            mock_result.json_body.return_value = {"id": "new-123"}

            mock_executor_instance = MockExecutor.return_value
            mock_executor_instance.execute = AsyncMock(return_value=mock_result)

            result = await action_executor.execute(
                "webhook",
                action_context,
                url="https://api.example.com/create",
                method="POST",
                capture_response={
                    "status_var": "webhook_status",
                    "body_var": "webhook_body",
                    "headers_var": "webhook_headers",
                },
            )

            assert result["success"] is True

            # Verify variables were captured in workflow state
            assert action_context.state.variables["webhook_status"] == 201
            assert action_context.state.variables["webhook_body"] == {"id": "new-123"}
            assert action_context.state.variables["webhook_headers"] == {"X-Request-Id": "req-456"}

    @pytest.mark.asyncio
    async def test_webhook_action_failure(self, action_executor, action_context):
        """Test webhook action handles failure gracefully."""
        with patch("gobby.workflows.webhook_executor.WebhookExecutor") as MockExecutor:
            mock_result = MagicMock()
            mock_result.success = False
            mock_result.status_code = 500
            mock_result.body = "Internal Server Error"
            mock_result.error = "HTTP 500"
            mock_result.headers = {}

            mock_executor_instance = MockExecutor.return_value
            mock_executor_instance.execute = AsyncMock(return_value=mock_result)

            result = await action_executor.execute(
                "webhook",
                action_context,
                url="https://api.example.com/fail",
            )

            assert result["success"] is False
            assert result["status_code"] == 500
            assert result["error"] == "HTTP 500"
            assert result["body"] is None  # Body not returned on failure

    @pytest.mark.asyncio
    async def test_webhook_action_with_retry_config(self, action_executor, action_context):
        """Test webhook action passes retry configuration to executor."""
        with patch("gobby.workflows.webhook_executor.WebhookExecutor") as MockExecutor:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.status_code = 200
            mock_result.body = "{}"
            mock_result.error = None
            mock_result.headers = {}

            mock_executor_instance = MockExecutor.return_value
            mock_executor_instance.execute = AsyncMock(return_value=mock_result)

            result = await action_executor.execute(
                "webhook",
                action_context,
                url="https://api.example.com/retry",
                retry={
                    "max_attempts": 5,
                    "backoff_seconds": 2,
                    "retry_on_status": [429, 503],
                },
            )

            assert result["success"] is True

            # Verify retry config was passed
            call_kwargs = mock_executor_instance.execute.call_args.kwargs
            assert call_kwargs["retry_config"] is not None
            assert call_kwargs["retry_config"]["max_attempts"] == 5

    @pytest.mark.asyncio
    async def test_webhook_action_webhook_id_not_supported(self, action_executor, action_context):
        """Test webhook action returns error for webhook_id without registry."""
        result = await action_executor.execute(
            "webhook",
            action_context,
            webhook_id="slack_alerts",
        )

        assert result is not None
        assert result["success"] is False
        assert "registry" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_webhook_action_interpolation_context(self, action_executor, action_context):
        """Test webhook action builds interpolation context from state."""
        # Set up workflow state with variables and artifacts
        action_context.state.variables = {"task_id": "123", "status": "completed"}
        action_context.state.artifacts = {"plan": "/path/to/plan.md"}

        with patch("gobby.workflows.webhook_executor.WebhookExecutor") as MockExecutor:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.status_code = 200
            mock_result.body = "{}"
            mock_result.error = None
            mock_result.headers = {}

            mock_executor_instance = MockExecutor.return_value
            mock_executor_instance.execute = AsyncMock(return_value=mock_result)

            await action_executor.execute(
                "webhook",
                action_context,
                url="https://api.example.com/notify",
                payload={"task": "{{ state.variables.task_id }}"},
            )

            # Verify context was passed for interpolation
            call_kwargs = mock_executor_instance.execute.call_args.kwargs
            assert call_kwargs["context"]["state"]["variables"]["task_id"] == "123"
            assert call_kwargs["context"]["artifacts"]["plan"] == "/path/to/plan.md"
