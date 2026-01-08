"""Integration tests for terminal mode with worktrees.

These tests verify the terminal spawn preparation, environment variable setup,
and integration with worktrees for agent spawning.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from gobby.agents.constants import (
    GOBBY_AGENT_DEPTH,
    GOBBY_AGENT_RUN_ID,
    GOBBY_MAX_AGENT_DEPTH,
    GOBBY_PARENT_SESSION_ID,
    GOBBY_PROJECT_ID,
    GOBBY_PROMPT,
    GOBBY_PROMPT_FILE,
    GOBBY_SESSION_ID,
    GOBBY_WORKFLOW_NAME,
    get_terminal_env_vars,
)
from gobby.agents.session import ChildSessionManager
from gobby.agents.spawn import (
    MAX_ENV_PROMPT_LENGTH,
    HeadlessResult,
    HeadlessSpawner,
    PreparedSpawn,
    SpawnMode,
    SpawnResult,
    TerminalSpawner,
    TerminalType,
    prepare_terminal_spawn,
    read_prompt_from_env,
)
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.projects import LocalProjectManager
from gobby.storage.sessions import LocalSessionManager


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = LocalDatabase(str(db_path))
        run_migrations(db)
        yield db


@pytest.fixture
def project(temp_db, tmp_path):
    """Create a test project."""
    project_manager = LocalProjectManager(temp_db)
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir(parents=True, exist_ok=True)
    return project_manager.create(
        name="test-project",
        repo_path=str(repo_path),
    )


@pytest.fixture
def session_storage(temp_db):
    """Create a session storage."""
    return LocalSessionManager(temp_db)


@pytest.fixture
def child_session_manager(session_storage):
    """Create a child session manager."""
    return ChildSessionManager(session_storage=session_storage, max_agent_depth=3)


@pytest.fixture
def parent_session(session_storage, project):
    """Create a parent session for testing."""
    return session_storage.register(
        machine_id="test-machine",
        source="claude",
        project_id=project.id,
        external_id="ext-parent-terminal",
        title="Parent Session",
    )


@pytest.fixture
def worktree_dir():
    """Create a temporary directory simulating a worktree."""
    with tempfile.TemporaryDirectory() as tmpdir:
        worktree_path = Path(tmpdir) / "worktree-feature-x"
        worktree_path.mkdir(parents=True)
        # Create a .git file to simulate worktree
        (worktree_path / ".git").write_text("gitdir: /main/.git/worktrees/feature-x")
        yield worktree_path


class TestGetTerminalEnvVars:
    """Tests for get_terminal_env_vars function."""

    def test_basic_env_vars(self):
        """Test basic environment variable generation."""
        result = get_terminal_env_vars(
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
        )

        assert result[GOBBY_SESSION_ID] == "sess-123"
        assert result[GOBBY_PARENT_SESSION_ID] == "sess-parent"
        assert result[GOBBY_AGENT_RUN_ID] == "run-456"
        assert result[GOBBY_PROJECT_ID] == "proj-789"
        assert result[GOBBY_AGENT_DEPTH] == "1"
        assert result[GOBBY_MAX_AGENT_DEPTH] == "3"

    def test_with_workflow_name(self):
        """Test env vars include workflow name when provided."""
        result = get_terminal_env_vars(
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            workflow_name="plan-execute",
        )

        assert result[GOBBY_WORKFLOW_NAME] == "plan-execute"

    def test_without_workflow_name(self):
        """Test workflow name omitted when not provided."""
        result = get_terminal_env_vars(
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            workflow_name=None,
        )

        assert GOBBY_WORKFLOW_NAME not in result

    def test_with_custom_depth(self):
        """Test env vars with custom depth values."""
        result = get_terminal_env_vars(
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            agent_depth=2,
            max_agent_depth=5,
        )

        assert result[GOBBY_AGENT_DEPTH] == "2"
        assert result[GOBBY_MAX_AGENT_DEPTH] == "5"

    def test_with_inline_prompt(self):
        """Test env vars with inline prompt."""
        result = get_terminal_env_vars(
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            prompt="Implement the feature",
        )

        assert result[GOBBY_PROMPT] == "Implement the feature"
        assert GOBBY_PROMPT_FILE not in result

    def test_with_prompt_file(self):
        """Test env vars with prompt file path."""
        result = get_terminal_env_vars(
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            prompt_file="/tmp/prompt.txt",
        )

        assert result[GOBBY_PROMPT_FILE] == "/tmp/prompt.txt"
        assert GOBBY_PROMPT not in result

    def test_all_values_are_strings(self):
        """Test all env var values are strings."""
        result = get_terminal_env_vars(
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
            workflow_name="test",
            agent_depth=2,
            max_agent_depth=5,
        )

        for key, value in result.items():
            assert isinstance(value, str), f"Value for {key} should be string"


class TestPrepareTerminalSpawn:
    """Tests for prepare_terminal_spawn function."""

    def test_creates_child_session(self, child_session_manager, parent_session, project):
        """Test that prepare_terminal_spawn creates a child session."""
        result = prepare_terminal_spawn(
            session_manager=child_session_manager,
            parent_session_id=parent_session.id,
            project_id=project.id,
            machine_id="test-machine",
            source="claude",
        )

        assert isinstance(result, PreparedSpawn)
        assert result.session_id is not None
        assert result.agent_run_id.startswith("run-")
        assert result.parent_session_id == parent_session.id
        assert result.project_id == project.id

    def test_sets_agent_depth(self, child_session_manager, parent_session, project):
        """Test that agent depth is correctly set."""
        result = prepare_terminal_spawn(
            session_manager=child_session_manager,
            parent_session_id=parent_session.id,
            project_id=project.id,
            machine_id="test-machine",
            source="claude",
        )

        # Parent is at depth 0, child should be at depth 1
        assert result.agent_depth == 1
        assert result.env_vars[GOBBY_AGENT_DEPTH] == "1"

    def test_with_workflow_name(self, child_session_manager, parent_session, project):
        """Test with workflow name."""
        result = prepare_terminal_spawn(
            session_manager=child_session_manager,
            parent_session_id=parent_session.id,
            project_id=project.id,
            machine_id="test-machine",
            source="claude",
            workflow_name="plan-execute",
        )

        assert result.workflow_name == "plan-execute"
        assert result.env_vars[GOBBY_WORKFLOW_NAME] == "plan-execute"

    def test_short_prompt_uses_env_var(self, child_session_manager, parent_session, project):
        """Test that short prompts are passed via environment variable."""
        short_prompt = "Implement a simple feature"

        result = prepare_terminal_spawn(
            session_manager=child_session_manager,
            parent_session_id=parent_session.id,
            project_id=project.id,
            machine_id="test-machine",
            source="claude",
            prompt=short_prompt,
        )

        assert result.env_vars[GOBBY_PROMPT] == short_prompt
        assert GOBBY_PROMPT_FILE not in result.env_vars

    def test_long_prompt_uses_file(self, child_session_manager, parent_session, project):
        """Test that long prompts are written to a file."""
        long_prompt = "x" * (MAX_ENV_PROMPT_LENGTH + 100)

        result = prepare_terminal_spawn(
            session_manager=child_session_manager,
            parent_session_id=parent_session.id,
            project_id=project.id,
            machine_id="test-machine",
            source="claude",
            prompt=long_prompt,
        )

        assert GOBBY_PROMPT not in result.env_vars
        assert GOBBY_PROMPT_FILE in result.env_vars

        # Verify file exists and contains prompt
        prompt_file = Path(result.env_vars[GOBBY_PROMPT_FILE])
        assert prompt_file.exists()
        assert prompt_file.read_text() == long_prompt

    def test_max_agent_depth_passed(self, child_session_manager, parent_session, project):
        """Test that max_agent_depth is correctly passed."""
        result = prepare_terminal_spawn(
            session_manager=child_session_manager,
            parent_session_id=parent_session.id,
            project_id=project.id,
            machine_id="test-machine",
            source="claude",
            max_agent_depth=5,
        )

        assert result.env_vars[GOBBY_MAX_AGENT_DEPTH] == "5"

    def test_env_vars_contains_all_required(self, child_session_manager, parent_session, project):
        """Test that env_vars contains all required variables."""
        result = prepare_terminal_spawn(
            session_manager=child_session_manager,
            parent_session_id=parent_session.id,
            project_id=project.id,
            machine_id="test-machine",
            source="claude",
        )

        required_vars = [
            GOBBY_SESSION_ID,
            GOBBY_PARENT_SESSION_ID,
            GOBBY_AGENT_RUN_ID,
            GOBBY_PROJECT_ID,
            GOBBY_AGENT_DEPTH,
            GOBBY_MAX_AGENT_DEPTH,
        ]

        for var in required_vars:
            assert var in result.env_vars


class TestReadPromptFromEnv:
    """Tests for read_prompt_from_env function."""

    def test_returns_none_when_not_set(self, monkeypatch):
        """Test returns None when no prompt environment variables set."""
        monkeypatch.delenv(GOBBY_PROMPT, raising=False)
        monkeypatch.delenv(GOBBY_PROMPT_FILE, raising=False)

        result = read_prompt_from_env()

        assert result is None

    def test_reads_inline_prompt(self, monkeypatch):
        """Test reads inline prompt from GOBBY_PROMPT."""
        monkeypatch.setenv(GOBBY_PROMPT, "Implement the feature")
        monkeypatch.delenv(GOBBY_PROMPT_FILE, raising=False)

        result = read_prompt_from_env()

        assert result == "Implement the feature"

    def test_reads_prompt_from_file(self, monkeypatch):
        """Test reads prompt from file specified in GOBBY_PROMPT_FILE."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("This is a long prompt from file")
            prompt_path = f.name

        try:
            monkeypatch.setenv(GOBBY_PROMPT_FILE, prompt_path)
            monkeypatch.delenv(GOBBY_PROMPT, raising=False)

            result = read_prompt_from_env()

            assert result == "This is a long prompt from file"
        finally:
            Path(prompt_path).unlink()

    def test_file_takes_priority(self, monkeypatch):
        """Test that prompt file takes priority over inline prompt."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Prompt from file")
            prompt_path = f.name

        try:
            monkeypatch.setenv(GOBBY_PROMPT_FILE, prompt_path)
            monkeypatch.setenv(GOBBY_PROMPT, "Inline prompt")

            result = read_prompt_from_env()

            assert result == "Prompt from file"
        finally:
            Path(prompt_path).unlink()

    def test_fallback_to_inline_when_file_missing(self, monkeypatch):
        """Test falls back to inline prompt when file doesn't exist."""
        monkeypatch.setenv(GOBBY_PROMPT_FILE, "/nonexistent/prompt.txt")
        monkeypatch.setenv(GOBBY_PROMPT, "Fallback prompt")

        result = read_prompt_from_env()

        assert result == "Fallback prompt"


class TestTerminalSpawnerDetection:
    """Tests for terminal type detection."""

    def test_get_available_terminals(self):
        """Test getting available terminals."""
        spawner = TerminalSpawner()
        available = spawner.get_available_terminals()

        # Should return a list (may be empty in CI)
        assert isinstance(available, list)

    def test_get_preferred_terminal(self):
        """Test getting preferred terminal."""
        spawner = TerminalSpawner()
        preferred = spawner.get_preferred_terminal()

        # May be None in CI without terminals
        assert preferred is None or isinstance(preferred, TerminalType)

    def test_auto_detection_with_no_terminals(self):
        """Test auto-detection when no terminals available."""
        spawner = TerminalSpawner()

        # Patch get_preferred_terminal to return None (no terminals available)
        with patch.object(spawner, "get_preferred_terminal", return_value=None):
            result = spawner.spawn(
                command=["echo", "test"],
                cwd="/tmp",
                terminal=TerminalType.AUTO,
            )

            assert result.success is False
            assert "No supported terminal" in result.message

    def test_spawn_with_unavailable_terminal(self):
        """Test spawning with unavailable terminal type."""
        spawner = TerminalSpawner()

        # Try to spawn with a specific terminal that's likely unavailable
        result = spawner.spawn(
            command=["echo", "test"],
            cwd="/tmp",
            terminal=TerminalType.KONSOLE,  # Unlikely on macOS
        )

        # Should fail gracefully if not available
        if result.success is False:
            assert "not available" in result.message.lower()


class TestHeadlessSpawner:
    """Tests for headless spawner functionality."""

    def test_spawn_simple_command(self):
        """Test spawning a simple command in headless mode."""
        spawner = HeadlessSpawner()

        result = spawner.spawn(
            command=["echo", "hello"],
            cwd="/tmp",
        )

        assert result.success is True
        assert result.pid is not None
        assert result.process is not None

        # Wait for process and check output
        stdout, _ = result.process.communicate()
        assert "hello" in stdout

    def test_spawn_with_env_vars(self):
        """Test spawning with custom environment variables."""
        spawner = HeadlessSpawner()

        result = spawner.spawn(
            command=["printenv", "TEST_VAR"],
            cwd="/tmp",
            env={"TEST_VAR": "test_value"},
        )

        assert result.success is True
        stdout, _ = result.process.communicate()
        assert "test_value" in stdout

    def test_spawn_agent_sets_env_vars(self):
        """Test spawn_agent sets Gobby environment variables."""
        spawner = HeadlessSpawner()

        result = spawner.spawn_agent(
            cli="printenv",
            cwd="/tmp",
            session_id="sess-123",
            parent_session_id="sess-parent",
            agent_run_id="run-456",
            project_id="proj-789",
        )

        assert result.success is True
        stdout, _ = result.process.communicate()

        # Check that Gobby env vars are set
        assert "sess-123" in stdout
        assert "sess-parent" in stdout

    def test_spawn_nonexistent_command(self):
        """Test spawning a non-existent command fails gracefully."""
        spawner = HeadlessSpawner()

        result = spawner.spawn(
            command=["nonexistent_command_12345"],
            cwd="/tmp",
        )

        assert result.success is False
        assert result.error is not None


class TestSpawnModeEnum:
    """Tests for SpawnMode enum."""

    def test_spawn_mode_values(self):
        """Test SpawnMode enum values."""
        assert SpawnMode.TERMINAL.value == "terminal"
        assert SpawnMode.EMBEDDED.value == "embedded"
        assert SpawnMode.HEADLESS.value == "headless"
        assert SpawnMode.IN_PROCESS.value == "in_process"

    def test_spawn_mode_from_string(self):
        """Test creating SpawnMode from string."""
        assert SpawnMode("terminal") == SpawnMode.TERMINAL
        assert SpawnMode("headless") == SpawnMode.HEADLESS


class TestTerminalTypeEnum:
    """Tests for TerminalType enum."""

    def test_terminal_type_values(self):
        """Test TerminalType enum values."""
        assert TerminalType.GHOSTTY.value == "ghostty"
        assert TerminalType.ITERM.value == "iterm"
        assert TerminalType.KITTY.value == "kitty"
        assert TerminalType.AUTO.value == "auto"

    def test_terminal_type_from_string(self):
        """Test creating TerminalType from string."""
        assert TerminalType("ghostty") == TerminalType.GHOSTTY
        assert TerminalType("auto") == TerminalType.AUTO


class TestWorktreeIntegration:
    """Tests for terminal mode integration with worktrees."""

    def test_prepare_spawn_with_worktree_path(
        self, child_session_manager, parent_session, project, worktree_dir
    ):
        """Test preparing spawn with a worktree as working directory."""
        result = prepare_terminal_spawn(
            session_manager=child_session_manager,
            parent_session_id=parent_session.id,
            project_id=project.id,
            machine_id="test-machine",
            source="claude",
            git_branch="feature-x",
        )

        assert result.session_id is not None
        # The session would track the git branch for the worktree

    def test_headless_spawn_in_worktree(self, worktree_dir):
        """Test headless spawning in a worktree directory."""
        spawner = HeadlessSpawner()

        result = spawner.spawn(
            command=["pwd"],
            cwd=str(worktree_dir),
        )

        assert result.success is True
        stdout, _ = result.process.communicate()
        assert "worktree-feature-x" in stdout

    def test_env_vars_for_worktree_agent(self, child_session_manager, parent_session, project):
        """Test that environment variables are correctly set for worktree agents."""
        result = prepare_terminal_spawn(
            session_manager=child_session_manager,
            parent_session_id=parent_session.id,
            project_id=project.id,
            machine_id="test-machine",
            source="claude",
            workflow_name="isolated-work",
            git_branch="feature-worktree",
            prompt="Work in this isolated worktree",
        )

        # Verify all required env vars are present
        assert GOBBY_SESSION_ID in result.env_vars
        assert GOBBY_PROJECT_ID in result.env_vars
        assert result.env_vars[GOBBY_WORKFLOW_NAME] == "isolated-work"
        assert result.env_vars[GOBBY_PROMPT] == "Work in this isolated worktree"


class TestPreparedSpawnDataclass:
    """Tests for PreparedSpawn dataclass."""

    def test_prepared_spawn_fields(self):
        """Test PreparedSpawn has correct fields."""
        spawn = PreparedSpawn(
            session_id="sess-123",
            agent_run_id="run-456",
            parent_session_id="sess-parent",
            project_id="proj-789",
            workflow_name="test-workflow",
            agent_depth=2,
            env_vars={"KEY": "value"},
        )

        assert spawn.session_id == "sess-123"
        assert spawn.agent_run_id == "run-456"
        assert spawn.parent_session_id == "sess-parent"
        assert spawn.project_id == "proj-789"
        assert spawn.workflow_name == "test-workflow"
        assert spawn.agent_depth == 2
        assert spawn.env_vars == {"KEY": "value"}

    def test_prepared_spawn_optional_workflow(self):
        """Test PreparedSpawn with optional workflow."""
        spawn = PreparedSpawn(
            session_id="sess-123",
            agent_run_id="run-456",
            parent_session_id="sess-parent",
            project_id="proj-789",
            workflow_name=None,
            agent_depth=1,
            env_vars={},
        )

        assert spawn.workflow_name is None


class TestSpawnResultDataclass:
    """Tests for SpawnResult dataclass."""

    def test_spawn_result_success(self):
        """Test SpawnResult for successful spawn."""
        result = SpawnResult(
            success=True,
            message="Spawned successfully",
            pid=12345,
            terminal_type="ghostty",
        )

        assert result.success is True
        assert result.pid == 12345
        assert result.terminal_type == "ghostty"
        assert result.error is None

    def test_spawn_result_failure(self):
        """Test SpawnResult for failed spawn."""
        result = SpawnResult(
            success=False,
            message="Failed to spawn",
            error="Terminal not available",
        )

        assert result.success is False
        assert result.pid is None
        assert result.error == "Terminal not available"


class TestHeadlessResultDataclass:
    """Tests for HeadlessResult dataclass."""

    def test_headless_result_get_output(self):
        """Test HeadlessResult.get_output method."""
        result = HeadlessResult(
            success=True,
            message="Running",
            pid=12345,
            output_buffer=["line1", "line2", "line3"],
        )

        output = result.get_output()
        assert output == "line1\nline2\nline3"

    def test_headless_result_empty_output(self):
        """Test HeadlessResult with empty output."""
        result = HeadlessResult(
            success=True,
            message="Running",
            pid=12345,
        )

        assert result.get_output() == ""
