"""Integration tests for compact handoff flow.

Tests the inject_context source=compact_handoff path:
- session.compact_markdown is read and returned for injection
- Missing compact_markdown is handled gracefully

Note: The extraction side (pre_compact -> set_handoff_context) is now
an MCP tool tested in tests/mcp_proxy/tools/test_session_messages_coverage.py.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.workflows.actions import ActionContext, ActionExecutor
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.templates import TemplateEngine

pytestmark = pytest.mark.unit


@pytest.fixture
def action_executor(temp_db, session_manager):
    """Create an ActionExecutor for testing."""
    mock_config = MagicMock()
    mock_config.compression = None  # Prevent TextCompressor from initializing with MagicMock
    return ActionExecutor(
        temp_db,
        session_manager,
        MagicMock(spec=TemplateEngine),
        llm_service=AsyncMock(),
        transcript_processor=MagicMock(),
        config=mock_config,
        tool_proxy_getter=AsyncMock(),
    )


@pytest.fixture
def workflow_state():
    """Create a workflow state for testing.

    Note: Tests commonly override session_id with the actual session ID
    after creating sessions via session_manager.register(). The placeholder
    value is not used directly.
    """
    return WorkflowState(
        session_id="placeholder",
        workflow_name="session-handoff",
        step="compact",
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_inject_context_reads_compact_handoff(
    action_executor,
    session_manager,
    sample_project,
    workflow_state,
):
    """Test that inject_context with source=compact_handoff reads from current session.

    Note: /compact keeps the same session ID - it's a continuation, not a new session.
    The compact_markdown is saved to the current session during pre_compact, then
    read from the same session when the context window restarts with source=compact.
    """
    # Create a session with compact_markdown (simulating same session after compact)
    session = session_manager.register(
        external_id="test-ext-id",
        machine_id="test-machine",
        source="claude_code",
        project_id=sample_project["id"],
        title="Test Session",
    )

    # Save compact_markdown to the session (as pre_compact would do)
    test_markdown = "### Original Goal\nFix the bug"
    session_manager.update_compact_markdown(session.id, test_markdown)

    # Update workflow state with session ID
    workflow_state.session_id = session.id

    # Create action context
    context = ActionContext(
        session_id=session.id,
        state=workflow_state,
        db=action_executor.db,
        session_manager=session_manager,
        template_engine=MagicMock(spec=TemplateEngine),
        tool_proxy_getter=AsyncMock(),
    )

    # Execute inject_context with compact_handoff source
    result = await action_executor.execute("inject_context", context, source="compact_handoff")

    # Verify injection returns the session's own markdown
    assert result is not None
    assert "inject_context" in result
    assert result["inject_context"] == test_markdown


@pytest.mark.asyncio
async def test_inject_context_no_compact_markdown(
    action_executor,
    session_manager,
    sample_project,
    workflow_state,
):
    """Test inject_context gracefully handles missing compact_markdown."""
    session = session_manager.register(
        external_id="test-ext-id",
        machine_id="test-machine",
        source="claude_code",
        project_id=sample_project["id"],
    )
    workflow_state.session_id = session.id

    context = ActionContext(
        session_id=session.id,
        state=workflow_state,
        db=action_executor.db,
        session_manager=session_manager,
        template_engine=MagicMock(spec=TemplateEngine),
        tool_proxy_getter=AsyncMock(),
    )

    result = await action_executor.execute("inject_context", context, source="compact_handoff")

    # Should return None or empty when no compact_markdown exists
    assert result is None or result.get("inject_context") is None
