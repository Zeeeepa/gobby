import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli.sessions import sessions
from gobby.sessions.analyzer import HandoffContext
from gobby.storage.sessions import Session


@pytest.fixture
def mock_session_manager():
    with patch("gobby.cli.sessions.get_session_manager") as mock:
        yield mock.return_value


@pytest.fixture
def mock_message_manager():
    with patch("gobby.cli.sessions.get_message_manager") as mock:
        yield mock.return_value


@pytest.fixture
def mock_resolve_session_id():
    with patch("gobby.cli.sessions.resolve_session_id") as mock:
        yield mock


@pytest.fixture
def runner():
    return CliRunner()


def test_create_handoff_command_basic(runner, mock_session_manager, mock_resolve_session_id):
    """Test create-handoff with minimal arguments."""
    mock_resolve_session_id.return_value = "session-123"

    session = Session(
        id="session-123",
        project_id="proj-1",
        jsonl_path="/tmp/fake/transcript.jsonl",
        source="claude",
        external_id="ext-1",
        machine_id="machine-1",
        title="Session 1",
        status="active",
        summary_path=None,
        summary_markdown=None,
        compact_markdown=None,
        git_branch="main",
        parent_session_id=None,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )
    mock_session_manager.get.return_value = session

    # Mock file operations and external calls
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("builtins.open", new_callable=MagicMock) as mock_open,
        patch("gobby.sessions.analyzer.TranscriptAnalyzer.extract_handoff_context") as mock_extract,
        patch(
            "gobby.mcp_proxy.tools.session_messages._format_handoff_markdown",
            return_value="# Summary",
        ),
        patch("gobby.cli.sessions.get_session_manager", return_value=mock_session_manager),
    ):
        # Setup mock file read
        mock_open.return_value.__enter__.return_value = ['{"role": "user", "content": "hello"}']

        # Setup analyzer result
        mock_extract.return_value = HandoffContext(
            active_gobby_task=None,
            todo_state=[],
            files_modified=[],
            git_commits=[],
            initial_goal=False,
            git_status="",
        )

        result = runner.invoke(
            sessions, ["create-handoff", "--session-id", "session-123", "--output", "db"]
        )

        assert result.exit_code == 0
        assert "Created handoff context" in result.output
        mock_session_manager.update_compact_markdown.assert_called_with("session-123", "# Summary")


def test_create_handoff_no_session_found(runner, mock_session_manager, mock_resolve_session_id):
    """Test create-handoff when session not found."""
    mock_resolve_session_id.return_value = "session-123"
    mock_session_manager.get.return_value = None

    result = runner.invoke(sessions, ["create-handoff", "--session-id", "session-123"])

    assert result.exit_code == 0
    assert "Session not found" in result.output


def test_create_handoff_no_transcript(runner, mock_session_manager, mock_resolve_session_id):
    """Test create-handoff when session has no transcript path."""
    mock_resolve_session_id.return_value = "session-123"
    session = Session(
        id="session-123",
        project_id="proj-1",
        jsonl_path=None,
        external_id="ext-1",
        machine_id="machine-1",
        source="claude",
        title="Session 1",
        status="active",
        summary_path=None,
        summary_markdown=None,
        compact_markdown=None,
        git_branch="main",
        parent_session_id=None,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )
    mock_session_manager.get.return_value = session

    result = runner.invoke(sessions, ["create-handoff", "--session-id", "session-123"])

    assert result.exit_code == 0
    assert "has no transcript path" in result.output


def test_create_handoff_transcript_not_found(runner, mock_session_manager, mock_resolve_session_id):
    """Test create-handoff when transcript file missing."""
    mock_resolve_session_id.return_value = "session-123"
    session = Session(
        id="session-123",
        project_id="proj-1",
        jsonl_path="/tmp/missing.jsonl",
        external_id="ext-1",
        machine_id="machine-1",
        source="claude",
        title="Session 1",
        status="active",
        summary_path=None,
        summary_markdown=None,
        compact_markdown=None,
        git_branch="main",
        parent_session_id=None,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )
    mock_session_manager.get.return_value = session

    with patch("pathlib.Path.exists", return_value=False):
        result = runner.invoke(sessions, ["create-handoff", "--session-id", "session-123"])

    assert result.exit_code == 0
    assert "Transcript file not found" in result.output


def test_create_handoff_full_summary(runner, mock_session_manager, mock_resolve_session_id):
    """Test create-handoff with full summary generation."""
    mock_resolve_session_id.return_value = "session-123"
    session = Session(
        id="session-123",
        project_id="proj-1",
        jsonl_path="/tmp/fake/transcript.jsonl",
        external_id="ext-1",
        machine_id="machine-1",
        source="claude",
        title="Session 1",
        status="active",
        summary_path=None,
        summary_markdown=None,
        compact_markdown=None,
        git_branch="main",
        parent_session_id=None,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )
    mock_session_manager.get.return_value = session

    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("builtins.open", new_callable=MagicMock) as mock_open,
        patch("gobby.sessions.analyzer.TranscriptAnalyzer.extract_handoff_context") as mock_extract,
        patch(
            "gobby.mcp_proxy.tools.session_messages._format_handoff_markdown",
            return_value="# Compact",
        ),
        patch("gobby.config.app.load_config") as mock_config,
        patch("gobby.llm.claude.ClaudeLLMProvider") as mock_provider_cls,
        patch("gobby.sessions.transcripts.claude.ClaudeTranscriptParser"),
        patch("anyio.run", return_value="# Full Summary") as mock_anyio_run,
    ):
        # Mock file content
        mock_open.return_value.__enter__.return_value = ['{"role": "user", "content": "hi"}']

        # Mock analyzer
        mock_extract.return_value = HandoffContext(
            active_gobby_task=None,
            todo_state=[],
            files_modified=[],
            git_commits=[],
            initial_goal=False,
            git_status="",
        )

        # Mock config with prompt
        mock_config_obj = MagicMock()
        mock_config_obj.session_summary.prompt = "template"
        mock_config.return_value = mock_config_obj

        result = runner.invoke(
            sessions, ["create-handoff", "--session-id", "session-123", "--full", "--output", "db"]
        )

        assert result.exit_code == 0
        mock_session_manager.update_summary.assert_called_with(
            "session-123", summary_markdown="# Full Summary"
        )


def test_create_handoff_file_output(
    runner, mock_session_manager, mock_resolve_session_id, tmp_path
):
    """Test create-handoff saving to file."""
    mock_resolve_session_id.return_value = "session-123"
    session = Session(
        id="session-123",
        project_id="proj-1",
        jsonl_path="/tmp/fake/transcript.jsonl",
        external_id="ext-1",
        machine_id="machine-1",
        source="claude",
        title="Session 1",
        status="active",
        summary_path=None,
        summary_markdown=None,
        compact_markdown=None,
        git_branch="main",
        parent_session_id=None,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )
    mock_session_manager.get.return_value = session
    output_dir = tmp_path / "summaries"

    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("builtins.open", new_callable=MagicMock) as mock_open,
        patch("gobby.sessions.analyzer.TranscriptAnalyzer.extract_handoff_context") as mock_extract,
        patch(
            "gobby.mcp_proxy.tools.session_messages._format_handoff_markdown",
            return_value="# Summary",
        ),
    ):
        mock_open.return_value.__enter__.return_value = ['{"role": "user", "content": "hi"}']
        mock_extract.return_value = HandoffContext(
            active_gobby_task=None,
            todo_state=[],
            files_modified=[],
            git_commits=[],
            initial_goal=False,
            git_status="",
        )

        result = runner.invoke(
            sessions,
            [
                "create-handoff",
                "--session-id",
                "session-123",
                "--compact",
                "--output",
                "file",
                "--path",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0
        # Verify file creation
        assert len(list(output_dir.glob("session_compact_*.md"))) == 1


def test_stats_command(runner, mock_session_manager, mock_message_manager):
    """Test stats command."""
    mock_session_manager.list.return_value = [
        Session(
            id="1",
            status="active",
            source="claude",
            project_id="proj-1",
            external_id="ext-1",
            machine_id="machine-1",
            title="S1",
            jsonl_path=None,
            summary_path=None,
            summary_markdown=None,
            compact_markdown=None,
            git_branch=None,
            parent_session_id=None,
            created_at="",
            updated_at="",
        ),
        Session(
            id="2",
            status="completed",
            source="gemini",
            project_id="proj-1",
            external_id="ext-2",
            machine_id="machine-1",
            title="S2",
            jsonl_path=None,
            summary_path=None,
            summary_markdown=None,
            compact_markdown=None,
            git_branch=None,
            parent_session_id=None,
            created_at="",
            updated_at="",
        ),
    ]

    # Mock message counts via async run
    mock_message_manager.get_all_counts = MagicMock()
    with patch("asyncio.run", return_value={"1": 10, "2": 5}):
        result = runner.invoke(sessions, ["stats"])

        assert result.exit_code == 0
        assert "Total Sessions: 2" in result.output
        assert "Total Messages: 15" in result.output
        assert "active: 1" in result.output
        assert "claude: 1" in result.output


def test_delete_command(runner, mock_session_manager, mock_resolve_session_id):
    """Test delete command."""
    mock_resolve_session_id.return_value = "session-123"
    session = Session(
        id="session-123",
        status="completed",
        project_id="proj-1",
        external_id="ext-1",
        machine_id="machine-1",
        source="claude",
        title="S1",
        jsonl_path=None,
        summary_path=None,
        summary_markdown=None,
        compact_markdown=None,
        git_branch=None,
        parent_session_id=None,
        created_at="",
        updated_at="",
    )
    mock_session_manager.get.return_value = session
    mock_session_manager.delete.return_value = True

    result = runner.invoke(sessions, ["delete", "session-123", "--yes"])

    assert result.exit_code == 0
    assert "Deleted session: session-123" in result.output
    mock_session_manager.delete.assert_called_with("session-123")


def test_delete_command_not_found(runner, mock_session_manager, mock_resolve_session_id):
    """Test delete command when session missing."""
    mock_resolve_session_id.return_value = "session-123"
    mock_session_manager.get.return_value = None

    result = runner.invoke(sessions, ["delete", "session-123", "--yes"])

    assert result.exit_code == 0
    assert "Session not found" in result.output
