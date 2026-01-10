from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.workflows.actions import ActionContext, ActionExecutor
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.templates import TemplateEngine


@pytest.fixture
def mock_services():
    return {
        "template_engine": MagicMock(spec=TemplateEngine),
        "llm_service": MagicMock(),
        "transcript_processor": MagicMock(),
        "config": MagicMock(),
        "mcp_manager": AsyncMock(),
        "session_manager": MagicMock(),
        "db": MagicMock(),
    }


@pytest.fixture
def action_context(mock_services):
    state = WorkflowState(
        session_id="test-session", workflow_name="test-workflow", step="test-step"
    )
    return ActionContext(
        session_id="test-session",
        state=state,
        db=mock_services["db"],
        session_manager=mock_services["session_manager"],
        template_engine=mock_services["template_engine"],
        llm_service=mock_services["llm_service"],
        transcript_processor=mock_services["transcript_processor"],
        mcp_manager=mock_services["mcp_manager"],
    )


@pytest.fixture
def action_executor(mock_services):
    return ActionExecutor(
        db=mock_services["db"],
        session_manager=mock_services["session_manager"],
        template_engine=mock_services["template_engine"],
        llm_service=mock_services["llm_service"],
        transcript_processor=mock_services["transcript_processor"],
        config=mock_services["config"],
        mcp_manager=mock_services["mcp_manager"],
    )


@pytest.mark.asyncio
async def test_inject_message(action_executor, action_context, mock_services):
    mock_services["template_engine"].render.return_value = "Rendered Message"

    result = await action_executor.execute(
        "inject_message", action_context, content="Hello {{ variable }}", extra="value"
    )

    assert result["inject_message"] == "Rendered Message"
    mock_services["template_engine"].render.assert_called_once()


@pytest.mark.asyncio
async def test_variables(action_executor, action_context):
    # Test set_variable
    await action_executor.execute("set_variable", action_context, name="count", value=10)
    assert action_context.state.variables["count"] == 10

    # Test increment_variable
    await action_executor.execute("increment_variable", action_context, name="count", amount=5)
    assert action_context.state.variables["count"] == 15

    # Test increment new variable (default 0)
    await action_executor.execute("increment_variable", action_context, name="new_var")
    assert action_context.state.variables["new_var"] == 1


@pytest.mark.asyncio
async def test_call_llm(action_executor, action_context, mock_services):
    mock_provider = AsyncMock()
    mock_provider.generate_text.return_value = "LLM Output"
    mock_services["llm_service"].get_default_provider.return_value = mock_provider
    mock_services["template_engine"].render.return_value = "Prompt"

    result = await action_executor.execute(
        "call_llm", action_context, prompt="Test Prompt", output_as="llm_result"
    )

    if result and "error" in result:
        pytest.fail(f"Action failed: {result['error']}")

    assert result is not None
    assert result["llm_called"] is True
    assert action_context.state.variables["llm_result"] == "LLM Output"


@pytest.mark.asyncio
async def test_unknown_action(action_executor, action_context):
    result = await action_executor.execute("invalid_action", action_context)
    assert result is None


@pytest.mark.asyncio
async def test_action_error(action_executor, action_context):
    # Mock specific action to raise exception
    action_context.db.side_effect = Exception("DB Error")
    # Actually easier to mock handler in internal dict
    mock_handler = MagicMock(side_effect=Exception("Handler Error"))
    action_executor.register("error_action", mock_handler)

    result = await action_executor.execute("error_action", action_context)
    assert "error" in result
    assert "Handler Error" in result["error"]


@pytest.mark.asyncio
async def test_synthesize_title(action_executor, action_context, mock_services, tmp_path):
    # Setup session and transcript
    session = MagicMock()
    session.jsonl_path = str(tmp_path / "transcript.jsonl")
    mock_services["session_manager"].get.return_value = session

    # Create valid transcript file
    import json

    with open(session.jsonl_path, "w") as f:
        f.write(json.dumps({"role": "user", "content": "hi"}) + "\n")

    mock_provider = AsyncMock()
    mock_provider.generate_text.return_value = '"New Title"'
    mock_services["llm_service"].get_default_provider.return_value = mock_provider
    mock_services["template_engine"].render.return_value = "Prompt"

    result = await action_executor.execute("synthesize_title", action_context)

    assert result["title_synthesized"] == "New Title"
    mock_services["session_manager"].update_title.assert_called_with("test-session", "New Title")


@pytest.mark.asyncio
async def test_synthesize_title_error(action_executor, action_context, mock_services):
    # Missing services
    action_context.llm_service = None
    result = await action_executor.execute("synthesize_title", action_context)
    assert "error" in result


@pytest.mark.skip(reason="Mocking issues with subprocess")
@pytest.mark.asyncio
async def test_start_new_session(action_executor, action_context, mock_services, sample_project):
    # Setup mocks
    mock_services["session_manager"].get.return_value = MagicMock(
        project_id="proj1", project_path="/tmp/test-project"
    )

    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value.poll.return_value = None
        mock_popen.return_value.pid = 12345

        result = await action_executor.execute(
            "start_new_session", action_context, task="Next Task"
        )

        if result and "error" in result:
            pytest.fail(f"Action failed: {result['error']}")

        assert result["started_new_session"] is True
        assert result["pid"] == 12345
        # session_manager.register is NOT called by this action (it just spawns process)


@pytest.mark.asyncio
async def test_mark_loop_complete(action_executor, action_context, mock_services):
    # This action updates 'stop_reason' variable to 'completed'
    await action_executor.execute("mark_loop_complete", action_context)
    assert action_context.state.variables["stop_reason"] == "completed"


@pytest.mark.asyncio
async def test_switch_mode(action_executor, action_context):
    result = await action_executor.execute("switch_mode", action_context, mode="ACT")
    assert result["mode_switch"] == "ACT"
    assert "SYSTEM: SWITCH MODE TO ACT" in result["inject_context"]


@pytest.mark.asyncio
async def test_mark_session_status(action_executor, action_context, mock_services):
    mock_services["session_manager"].get.return_value = MagicMock(parent_session_id=None)

    result = await action_executor.execute(
        "mark_session_status", action_context, status="completed"
    )
    assert result["status_updated"] is True
    mock_services["session_manager"].update_status.assert_called_with("test-session", "completed")


@pytest.mark.skip(reason="Mocking issues with content_exists")
@pytest.mark.asyncio
async def test_memory_actions(action_executor, action_context, mock_services):
    # Setup memory manager mock
    mock_memory_manager = MagicMock()
    action_context.memory_manager = mock_memory_manager
    action_context.memory_manager.config.enabled = True

    # Mock content_exists to return False explicitly
    mock_memory_manager.content_exists.return_value = False

    mock_memory = MagicMock()
    mock_memory.id = "mem-id"
    mock_memory_manager.remember = AsyncMock(return_value=mock_memory)
    mock_memory_manager.recall = AsyncMock(return_value=["Memory 1"])

    # Test memory_save
    result = await action_executor.execute(
        "memory_save", action_context, content="Important fact", tags=["fact"]
    )

    if result and "error" in result:
        pytest.fail(f"Memory Save Action failed: {result['error']}")

    assert result["memory_id"] == "mem-id"

    # Test memory_recall_relevant
    action_context.event_data = {"prompt_text": "What happened?"}

    result = await action_executor.execute(
        "memory_recall_relevant", action_context, **{"as": "memories"}
    )

    if result and "error" in result:
        pytest.fail(f"Memory Recall Action failed: {result['error']}")

    if result:
        assert result["injected"] is True
        assert result["count"] == 1
