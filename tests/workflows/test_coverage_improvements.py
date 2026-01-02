import asyncio
from unittest.mock import MagicMock, patch

import pytest

from gobby.llm.claude import ClaudeLLMProvider
from gobby.workflows.actions import ActionContext, ActionExecutor
from gobby.workflows.definitions import WorkflowState


@pytest.fixture
def mock_action_context():
    """Create a mock action context."""
    context = MagicMock(spec=ActionContext)
    context.session_id = "test-session"

    context.state = WorkflowState(
        session_id="test-session", workflow_name="test-workflow", step="test-step"
    )

    context.db = MagicMock()
    context.session_manager = MagicMock()
    context.session_manager.get.return_value = MagicMock(project_id="test-project")

    context.template_engine = MagicMock()

    # Simple render mock that replaces handlebars
    def simple_render(template, ctx):
        result = template
        if "{{ artifacts_list }}" in result:
            result = result.replace("{{ artifacts_list }}", ctx.get("artifacts_list", ""))
        if "{{ observations_text }}" in result:
            result = result.replace("{{ observations_text }}", ctx.get("observations_text", ""))
        if "{{ workflow_state_text }}" in result:
            result = result.replace("{{ workflow_state_text }}", ctx.get("workflow_state_text", ""))
        if "{{ handoff.notes }}" in result:
            # handoff is a dict in ctx
            handoff = ctx.get("handoff", {})
            notes = handoff.get("notes", "") if isinstance(handoff, dict) else ""
            result = result.replace("{{ handoff.notes }}", notes)
        return result

    context.template_engine.render.side_effect = simple_render

    executor = ActionExecutor(
        db=context.db,
        session_manager=context.session_manager,
        template_engine=context.template_engine,
    )
    context.executor = executor

    return context


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = MagicMock()
    config.code_execution.default_timeout = 30
    config.code_execution.max_turns = 1
    config.code_execution.model = "claude-3-haiku"
    config.session_summary.model = "claude-3-haiku"
    config.title_synthesis.model = "claude-3-haiku"
    return config


@pytest.mark.asyncio
async def test_inject_context_artifacts(mock_action_context):
    """Test injecting artifact context."""
    context = mock_action_context
    context.state.artifacts = {"test.txt": "/path/to/test.txt"}

    result = await context.executor.execute(
        "inject_context", context, source="artifacts", template="Artifacts: {{ artifacts_list }}"
    )
    assert (
        result["inject_context"]
        == "Artifacts: ## Captured Artifacts\n- test.txt: /path/to/test.txt"
    )


@pytest.mark.asyncio
async def test_inject_context_observations(mock_action_context):
    """Test injecting observation context."""
    context = mock_action_context
    context.state.observations = [{"step": 1, "result": "ok"}]

    result = await context.executor.execute(
        "inject_context", context, source="observations", template="Obs: {{ observations_text }}"
    )
    assert "Obs: ## Observations" in result["inject_context"]
    assert '"result": "ok"' in result["inject_context"]


@pytest.mark.asyncio
async def test_inject_context_workflow_state(mock_action_context):
    """Test injecting workflow state context."""
    context = mock_action_context
    context.state.variables = {"foo": "bar"}

    result = await context.executor.execute(
        "inject_context",
        context,
        source="workflow_state",
        template="State: {{ workflow_state_text }}",
    )
    assert "State: ## Workflow State" in result["inject_context"]
    assert '"foo": "bar"' in result["inject_context"]


@pytest.mark.asyncio
async def test_inject_context_compact_handoff(mock_action_context):
    """Test injecting compact handoff context."""
    context = mock_action_context
    mock_session = MagicMock()
    mock_session.compact_markdown = "Compact summary"
    context.session_manager.get.return_value = mock_session

    result = await context.executor.execute(
        "inject_context", context, source="compact_handoff", template="Handoff: {{ handoff.notes }}"
    )
    assert result["inject_context"] == "Handoff: Compact summary"


@pytest.mark.asyncio
async def test_inject_context_require_blocks_on_missing(mock_action_context):
    """Test inject_context with require=True blocks when no content found."""
    context = mock_action_context
    mock_session = MagicMock()
    mock_session.compact_markdown = None  # No handoff content
    context.session_manager.get.return_value = mock_session

    result = await context.executor.execute(
        "inject_context", context, source="compact_handoff", require=True
    )

    assert result["decision"] == "block"
    assert "Required handoff context not found" in result["reason"]


@pytest.mark.asyncio
async def test_inject_context_require_allows_with_content(mock_action_context):
    """Test inject_context with require=True allows when content found."""
    context = mock_action_context
    mock_session = MagicMock()
    mock_session.compact_markdown = "Test handoff content"
    context.session_manager.get.return_value = mock_session

    result = await context.executor.execute(
        "inject_context", context, source="compact_handoff", require=True
    )

    assert "inject_context" in result
    assert result["inject_context"] == "Test handoff content"


@pytest.mark.asyncio
async def test_read_artifact_glob(mock_action_context, tmp_path):
    """Test reading artifact with glob pattern."""
    context = mock_action_context
    test_file = tmp_path / "glob_test.txt"
    test_file.write_text("glob content")

    result = await context.executor.execute(
        "read_artifact", context, pattern=str(tmp_path / "*.txt"), **{"as": "glob_var"}
    )

    assert result["read_artifact"] is True
    assert context.state.variables["glob_var"] == "glob content"


@pytest.mark.asyncio
async def test_increment_variable_non_numeric(mock_action_context):
    """Test incrementing a non-numeric variable raises TypeError."""
    context = mock_action_context
    context.state.variables = {"counter": "string_value"}

    result = await context.executor.execute("increment_variable", context, name="counter", amount=1)

    # The action now raises TypeError which is caught and returned as error
    assert "error" in result
    assert "Cannot increment non-numeric" in result["error"]


@pytest.mark.asyncio
async def test_claude_cli_missing(mock_config):
    """Test Claude provider handles missing CLI."""
    with patch("shutil.which", return_value=None):
        provider = ClaudeLLMProvider(mock_config)
        assert provider._claude_cli_path is None

        result = await provider.generate_text("test")
        assert "Generation unavailable" in result

        result = await provider.execute_code("print('hi')", prompt_template="{code}")
        assert result["success"] is False
        assert "Claude CLI not found" in result["error"]


@pytest.mark.asyncio
async def test_claude_cli_retry_logic(mock_config):
    """Test Claude provider retries finding CLI."""
    # Setup: Init call finds it
    with (
        patch("shutil.which", return_value="/initial/path"),
        patch("os.path.exists", return_value=True),
        patch("os.access", return_value=True),
    ):
        provider = ClaudeLLMProvider(mock_config)

    # Configure sequence:
    # 1. verify calls _claude_cli_path check -> exists(/initial/path) -> False (triggers retry)
    # 2. First retry attempt -> finds new path immediately -> exists=True (success)

    def exists_side_effect(path):
        if path == "/initial/path":
            return False
        if path == "/new/path":
            return True
        return False

    s_exists = MagicMock(side_effect=exists_side_effect)

    # Return /new/path immediately on first retry call
    with (
        patch("shutil.which", return_value="/new/path"),
        patch("os.path.exists", s_exists),
        patch("time.sleep"),
    ):
        cli_path = provider._verify_cli_path()
        assert cli_path == "/new/path"


@pytest.mark.asyncio
async def test_claude_execute_code_timeout(mock_config):
    """Test Claude code execution timeout."""
    with (
        patch("shutil.which", return_value="/mock/claude"),
        patch("os.path.exists", return_value=True),
        patch("os.access", return_value=True),
    ):
        provider = ClaudeLLMProvider(mock_config)

        async def mock_query_hang(*args, **kwargs):
            await asyncio.sleep(0.2)
            yield "done"

        with patch("gobby.llm.claude.query", side_effect=mock_query_hang):
            result = await provider.execute_code(
                "print('long')", timeout=0.05, prompt_template="{code}"
            )

            assert result["success"] is False
            assert "timed out" in result["error"]


@pytest.mark.asyncio
async def test_call_llm_missing_service(mock_action_context):
    """Test call_llm handles missing LLM service."""
    context = mock_action_context
    context.llm_service = None

    result = await context.executor.execute("call_llm", context, prompt="test", output_as="var")

    assert "error" in result
    assert "Missing LLM service" in result["error"]
