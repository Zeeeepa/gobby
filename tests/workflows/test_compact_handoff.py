"""Integration tests for compact handoff flow.

Tests the complete autocompact flow:
1. pre_compact hook triggers extract_handoff_context
2. Context is saved to session.compact_markdown
3. session_start triggers inject_context with source=compact_handoff
4. Context is returned for injection
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.config.app import CompactHandoffConfig, DaemonConfig
from gobby.workflows.actions import ActionContext, ActionExecutor
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.templates import TemplateEngine


@pytest.fixture
def sample_transcript(tmp_path):
    """Create a sample Claude Code transcript file."""
    transcript_path = tmp_path / "transcript.jsonl"

    turns = [
        {"type": "user", "message": {"content": "Fix the authentication bug"}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "I'll fix that for you."},
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "input": {"file_path": "/src/auth/login.py"},
                    },
                ]
            },
        },
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "git commit -m 'fix auth bug'"},
                    },
                    {
                        "type": "tool_use",
                        "name": "TodoWrite",
                        "input": {
                            "todos": [
                                {"content": "Fix auth bug", "status": "completed"},
                                {"content": "Add tests", "status": "in_progress"},
                            ]
                        },
                    },
                ]
            },
        },
    ]

    with open(transcript_path, "w") as f:
        for turn in turns:
            f.write(json.dumps(turn) + "\n")

    return transcript_path


@pytest.fixture
def mock_config():
    """Create a mock config with compact_handoff enabled."""
    config = MagicMock(spec=DaemonConfig)
    config.compact_handoff = CompactHandoffConfig(enabled=True)
    return config


@pytest.fixture
def action_executor(temp_db, session_manager):
    """Create an ActionExecutor for testing."""
    return ActionExecutor(
        temp_db,
        session_manager,
        MagicMock(spec=TemplateEngine),
        llm_service=AsyncMock(),
        transcript_processor=MagicMock(),
        config=MagicMock(),
        mcp_manager=AsyncMock(),
    )


@pytest.fixture
def workflow_state():
    """Create a workflow state for testing."""
    return WorkflowState(
        session_id="test-session",
        workflow_name="session-handoff",
        step="compact",
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_extract_handoff_context_saves_to_session(
    action_executor,
    session_manager,
    sample_project,
    sample_transcript,
    workflow_state,
    mock_config,
):
    """Test that extract_handoff_context saves markdown to session.compact_markdown."""
    # Create a session with the transcript path
    session = session_manager.register(
        external_id="test-ext-id",
        machine_id="test-machine",
        source="claude_code",
        project_id=sample_project["id"],
        title="Test Session",
        jsonl_path=str(sample_transcript),
    )

    # Update workflow state with real session ID
    workflow_state.session_id = session.id

    # Create action context
    context = ActionContext(
        session_id=session.id,
        state=workflow_state,
        db=action_executor.db,
        session_manager=session_manager,
        template_engine=MagicMock(spec=TemplateEngine),
        mcp_manager=AsyncMock(),
        config=mock_config,
    )

    # Mock git status
    with patch.object(action_executor, "_get_git_status", return_value="M src/auth/login.py"):
        result = await action_executor.execute("extract_handoff_context", context)

    # Verify extraction succeeded
    assert result is not None
    assert result.get("handoff_context_extracted") is True
    assert result.get("markdown_length", 0) > 0

    # Verify compact_markdown was saved to session
    updated_session = session_manager.get(session.id)
    assert updated_session is not None
    assert updated_session.compact_markdown is not None
    assert len(updated_session.compact_markdown) > 0

    # Verify content includes expected sections
    markdown = updated_session.compact_markdown
    assert "Fix the authentication bug" in markdown  # Initial goal
    assert "login.py" in markdown  # File modified


@pytest.mark.asyncio
@pytest.mark.integration
async def test_inject_context_reads_compact_handoff(
    action_executor,
    session_manager,
    sample_project,
    workflow_state,
):
    """Test that inject_context with source=compact_handoff reads from parent session."""
    # Create a parent session with compact_markdown
    parent_session = session_manager.register(
        external_id="parent-ext-id",
        machine_id="test-machine",
        source="claude_code",
        project_id=sample_project["id"],
        title="Parent Session",
    )

    # Save compact_markdown to parent session
    test_markdown = "### Original Goal\nFix the bug"
    session_manager.update_compact_markdown(parent_session.id, test_markdown)

    # Create child session linked to parent
    child_session = session_manager.register(
        external_id="child-ext-id",
        machine_id="test-machine",
        source="claude_code",
        project_id=sample_project["id"],
        title="Child Session",
        parent_session_id=parent_session.id,
    )

    # Update workflow state with child session ID
    workflow_state.session_id = child_session.id

    # Create action context
    context = ActionContext(
        session_id=child_session.id,
        state=workflow_state,
        db=action_executor.db,
        session_manager=session_manager,
        template_engine=MagicMock(spec=TemplateEngine),
        mcp_manager=AsyncMock(),
    )

    # Execute inject_context with compact_handoff source
    result = await action_executor.execute(
        "inject_context", context, source="compact_handoff"
    )

    # Verify injection returns the parent's markdown
    assert result is not None
    assert "inject_context" in result
    assert result["inject_context"] == test_markdown


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_compact_handoff_flow(
    action_executor,
    session_manager,
    sample_project,
    sample_transcript,
    workflow_state,
    mock_config,
):
    """Test the complete compact handoff flow: extract -> save -> inject via child session."""
    # Step 1: Create parent session with transcript
    parent_session = session_manager.register(
        external_id="parent-ext-id",
        machine_id="test-machine",
        source="claude_code",
        project_id=sample_project["id"],
        title="Parent Session",
        jsonl_path=str(sample_transcript),
    )
    workflow_state.session_id = parent_session.id

    # Step 2: Execute extract_handoff_context (simulating pre_compact)
    extract_context = ActionContext(
        session_id=parent_session.id,
        state=workflow_state,
        db=action_executor.db,
        session_manager=session_manager,
        template_engine=MagicMock(spec=TemplateEngine),
        mcp_manager=AsyncMock(),
        config=mock_config,
    )

    with patch.object(action_executor, "_get_git_status", return_value="M src/auth/login.py"):
        extract_result = await action_executor.execute(
            "extract_handoff_context", extract_context
        )

    assert extract_result.get("handoff_context_extracted") is True

    # Step 3: Verify compact_markdown is persisted
    session_after_extract = session_manager.get(parent_session.id)
    assert session_after_extract.compact_markdown is not None
    saved_markdown = session_after_extract.compact_markdown

    # Step 4: Create child session linked to parent (simulates post-compact new session)
    child_session = session_manager.register(
        external_id="child-ext-id",
        machine_id="test-machine",
        source="claude_code",
        project_id=sample_project["id"],
        title="Child Session",
        parent_session_id=parent_session.id,
    )

    # Step 5: Execute inject_context from child session (simulating session_start after compact)
    child_workflow_state = WorkflowState(
        session_id=child_session.id,
        workflow_name="session-handoff",
        step="compact",
    )
    inject_ctx = ActionContext(
        session_id=child_session.id,
        state=child_workflow_state,
        db=action_executor.db,
        session_manager=session_manager,
        template_engine=MagicMock(spec=TemplateEngine),
        mcp_manager=AsyncMock(),
    )

    inject_result = await action_executor.execute(
        "inject_context", inject_ctx, source="compact_handoff"
    )

    # Step 6: Verify injected context matches saved markdown from parent
    assert inject_result is not None
    assert inject_result.get("inject_context") == saved_markdown

    # Verify content integrity
    assert "Fix the authentication bug" in inject_result["inject_context"]
    assert "login.py" in inject_result["inject_context"]


@pytest.mark.asyncio
async def test_extract_handoff_context_disabled(
    action_executor,
    session_manager,
    sample_project,
    sample_transcript,
    workflow_state,
):
    """Test that extract_handoff_context respects enabled=False config."""
    session = session_manager.register(
        external_id="test-ext-id",
        machine_id="test-machine",
        source="claude_code",
        project_id=sample_project["id"],
        jsonl_path=str(sample_transcript),
    )
    workflow_state.session_id = session.id

    # Config with compact_handoff disabled
    disabled_config = MagicMock(spec=DaemonConfig)
    disabled_config.compact_handoff = CompactHandoffConfig(enabled=False)

    context = ActionContext(
        session_id=session.id,
        state=workflow_state,
        db=action_executor.db,
        session_manager=session_manager,
        template_engine=MagicMock(spec=TemplateEngine),
        mcp_manager=AsyncMock(),
        config=disabled_config,
    )

    result = await action_executor.execute("extract_handoff_context", context)

    # Should skip when disabled
    assert result is not None
    assert result.get("skipped") is True
    assert "disabled" in result.get("reason", "").lower()


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
        mcp_manager=AsyncMock(),
    )

    result = await action_executor.execute(
        "inject_context", context, source="compact_handoff"
    )

    # Should return None or empty when no compact_markdown exists
    assert result is None or result.get("inject_context") is None
