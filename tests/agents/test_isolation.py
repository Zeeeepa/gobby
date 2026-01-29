"""
Tests for Isolation Handlers.

Tests the isolation abstraction layer for spawn_agent unified API.
"""

from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.isolation import (
    CloneIsolationHandler,
    CurrentIsolationHandler,
    IsolationContext,
    IsolationHandler,
    SpawnConfig,
    WorktreeIsolationHandler,
    generate_branch_name,
    get_isolation_handler,
)


class TestIsolationContext:
    """Tests for IsolationContext dataclass."""

    def test_isolation_context_fields(self):
        """Test IsolationContext has all required fields."""
        ctx = IsolationContext(
            cwd="/path/to/project",
            branch_name="feature-branch",
            worktree_id="wt-123",
            clone_id="clone-456",
            isolation_type="worktree",
        )

        assert ctx.cwd == "/path/to/project"
        assert ctx.branch_name == "feature-branch"
        assert ctx.worktree_id == "wt-123"
        assert ctx.clone_id == "clone-456"
        assert ctx.isolation_type == "worktree"

    def test_isolation_context_defaults(self):
        """Test IsolationContext default values."""
        ctx = IsolationContext(cwd="/path/to/project")

        assert ctx.cwd == "/path/to/project"
        assert ctx.branch_name is None
        assert ctx.worktree_id is None
        assert ctx.clone_id is None
        assert ctx.isolation_type == "current"
        assert ctx.extra == {}

    def test_isolation_context_extra_dict(self):
        """Test IsolationContext extra dict for additional metadata."""
        ctx = IsolationContext(
            cwd="/path/to/project",
            extra={"main_repo_path": "/path/to/main"},
        )

        assert ctx.extra["main_repo_path"] == "/path/to/main"


class TestSpawnConfig:
    """Tests for SpawnConfig dataclass."""

    def test_spawn_config_fields(self):
        """Test SpawnConfig has all required fields."""
        config = SpawnConfig(
            prompt="Test prompt",
            task_id="task-123",
            task_title="Implement feature",
            task_seq_num=6121,
            branch_name=None,
            branch_prefix="feat/",
            base_branch="main",
            project_id="proj-456",
            project_path="/path/to/project",
            provider="claude",
            parent_session_id="session-789",
        )

        assert config.prompt == "Test prompt"
        assert config.task_id == "task-123"
        assert config.task_title == "Implement feature"
        assert config.task_seq_num == 6121
        assert config.branch_name is None
        assert config.branch_prefix == "feat/"
        assert config.base_branch == "main"
        assert config.project_id == "proj-456"
        assert config.project_path == "/path/to/project"
        assert config.provider == "claude"
        assert config.parent_session_id == "session-789"


class TestGenerateBranchName:
    """Tests for generate_branch_name function."""

    def test_explicit_branch_name_returned(self):
        """Test explicit branch_name is returned as-is."""
        config = SpawnConfig(
            prompt="Test",
            task_id=None,
            task_title=None,
            task_seq_num=None,
            branch_name="my-explicit-branch",
            branch_prefix=None,
            base_branch="main",
            project_id="proj",
            project_path="/path",
            provider="claude",
            parent_session_id="sess",
        )

        branch = generate_branch_name(config)
        assert branch == "my-explicit-branch"

    def test_branch_from_task_title(self):
        """Test branch generated from task title and seq_num."""
        config = SpawnConfig(
            prompt="Test",
            task_id="task-123",
            task_title="Implement Login Feature",
            task_seq_num=6079,
            branch_name=None,
            branch_prefix=None,
            base_branch="main",
            project_id="proj",
            project_path="/path",
            provider="claude",
            parent_session_id="sess",
        )

        branch = generate_branch_name(config)
        assert branch == "task-6079-implement-login-feature"

    def test_branch_from_task_title_slug_truncated(self):
        """Test branch slug is truncated to 40 chars."""
        config = SpawnConfig(
            prompt="Test",
            task_id="task-123",
            task_title="This is a very long task title that should be truncated to forty characters",
            task_seq_num=6079,
            branch_name=None,
            branch_prefix=None,
            base_branch="main",
            project_id="proj",
            project_path="/path",
            provider="claude",
            parent_session_id="sess",
        )

        branch = generate_branch_name(config)
        # Slug should be max 40 chars after "task-6079-"
        assert branch.startswith("task-6079-")
        slug_part = branch[len("task-6079-") :]
        assert len(slug_part) <= 40

    def test_branch_from_task_title_special_chars_removed(self):
        """Test special characters are removed from slug."""
        config = SpawnConfig(
            prompt="Test",
            task_id="task-123",
            task_title="Fix bug #123: Handle @user's input!",
            task_seq_num=6080,
            branch_name=None,
            branch_prefix=None,
            base_branch="main",
            project_id="proj",
            project_path="/path",
            provider="claude",
            parent_session_id="sess",
        )

        branch = generate_branch_name(config)
        # Only alphanumeric and hyphens should remain
        assert branch == "task-6080-fix-bug-123-handle-users-input"

    def test_fallback_to_prefix_timestamp(self):
        """Test fallback to prefix+timestamp when no task."""
        config = SpawnConfig(
            prompt="Test",
            task_id=None,
            task_title=None,
            task_seq_num=None,
            branch_name=None,
            branch_prefix="agent/",
            base_branch="main",
            project_id="proj",
            project_path="/path",
            provider="claude",
            parent_session_id="sess",
        )

        with patch("time.time", return_value=1706297600):
            branch = generate_branch_name(config)
            assert branch == "agent/1706297600"

    def test_fallback_default_prefix(self):
        """Test default prefix 'agent/' when no prefix specified."""
        config = SpawnConfig(
            prompt="Test",
            task_id=None,
            task_title=None,
            task_seq_num=None,
            branch_name=None,
            branch_prefix=None,
            base_branch="main",
            project_id="proj",
            project_path="/path",
            provider="claude",
            parent_session_id="sess",
        )

        with patch("time.time", return_value=1706297600):
            branch = generate_branch_name(config)
            assert branch == "agent/1706297600"


class TestCurrentIsolationHandler:
    """Tests for CurrentIsolationHandler."""

    @pytest.mark.asyncio
    async def test_prepare_environment_returns_project_path(self):
        """Test prepare_environment returns IsolationContext with project_path as cwd."""
        handler = CurrentIsolationHandler()
        config = SpawnConfig(
            prompt="Test prompt",
            task_id=None,
            task_title=None,
            task_seq_num=None,
            branch_name=None,
            branch_prefix=None,
            base_branch="main",
            project_id="proj-123",
            project_path="/path/to/my/project",
            provider="claude",
            parent_session_id="sess-456",
        )

        ctx = await handler.prepare_environment(config)

        assert ctx.cwd == "/path/to/my/project"
        assert ctx.isolation_type == "current"

    @pytest.mark.asyncio
    async def test_prepare_environment_no_branch_or_ids(self):
        """Test prepare_environment returns no branch, worktree_id, or clone_id."""
        handler = CurrentIsolationHandler()
        config = SpawnConfig(
            prompt="Test",
            task_id=None,
            task_title=None,
            task_seq_num=None,
            branch_name=None,
            branch_prefix=None,
            base_branch="main",
            project_id="proj",
            project_path="/path",
            provider="claude",
            parent_session_id="sess",
        )

        ctx = await handler.prepare_environment(config)

        assert ctx.branch_name is None
        assert ctx.worktree_id is None
        assert ctx.clone_id is None

    def test_build_context_prompt_returns_unchanged(self):
        """Test build_context_prompt returns original prompt unchanged."""
        handler = CurrentIsolationHandler()
        original_prompt = "Please implement the login feature."
        ctx = IsolationContext(cwd="/path/to/project")

        result = handler.build_context_prompt(original_prompt, ctx)

        assert result == original_prompt

    def test_is_isolation_handler_subclass(self):
        """Test CurrentIsolationHandler is a subclass of IsolationHandler."""
        assert issubclass(CurrentIsolationHandler, IsolationHandler)

    def test_isolation_handler_is_abstract(self):
        """Test IsolationHandler cannot be instantiated directly."""
        with pytest.raises(TypeError):
            IsolationHandler()  # type: ignore


class TestWorktreeIsolationHandler:
    """Tests for WorktreeIsolationHandler."""

    @pytest.mark.asyncio
    async def test_prepare_environment_creates_worktree(self):
        """Test prepare_environment creates worktree if not exists."""
        mock_git_manager = MagicMock()
        mock_git_manager.repo_path = "/path/to/main/repo"
        mock_git_manager.create_worktree.return_value = MagicMock(
            success=True,
            worktree_path="/tmp/worktrees/my-branch",
        )

        mock_worktree_storage = MagicMock()
        mock_worktree_storage.get_by_branch.return_value = None  # No existing worktree
        mock_worktree_storage.create.return_value = MagicMock(
            id="wt-123",
            worktree_path="/tmp/worktrees/my-branch",
            branch_name="my-branch",
        )

        handler = WorktreeIsolationHandler(
            git_manager=mock_git_manager,
            worktree_storage=mock_worktree_storage,
        )

        config = SpawnConfig(
            prompt="Test",
            task_id=None,
            task_title=None,
            task_seq_num=None,
            branch_name="my-branch",
            branch_prefix=None,
            base_branch="main",
            project_id="proj-123",
            project_path="/path/to/main/repo",
            provider="claude",
            parent_session_id="sess-456",
        )

        ctx = await handler.prepare_environment(config)

        assert ctx.isolation_type == "worktree"
        assert ctx.worktree_id == "wt-123"
        assert ctx.branch_name == "my-branch"
        mock_git_manager.create_worktree.assert_called_once()

    @pytest.mark.asyncio
    async def test_prepare_environment_reuses_existing_worktree(self):
        """Test prepare_environment reuses existing worktree for same branch."""
        mock_git_manager = MagicMock()
        mock_git_manager.repo_path = "/path/to/main/repo"

        mock_worktree_storage = MagicMock()
        mock_worktree_storage.get_by_branch.return_value = MagicMock(
            id="existing-wt-456",
            worktree_path="/tmp/worktrees/existing-branch",
            branch_name="existing-branch",
        )

        handler = WorktreeIsolationHandler(
            git_manager=mock_git_manager,
            worktree_storage=mock_worktree_storage,
        )

        config = SpawnConfig(
            prompt="Test",
            task_id=None,
            task_title=None,
            task_seq_num=None,
            branch_name="existing-branch",
            branch_prefix=None,
            base_branch="main",
            project_id="proj-123",
            project_path="/path/to/main/repo",
            provider="claude",
            parent_session_id="sess-456",
        )

        ctx = await handler.prepare_environment(config)

        assert ctx.worktree_id == "existing-wt-456"
        assert ctx.cwd == "/tmp/worktrees/existing-branch"
        # Should NOT create a new worktree
        mock_git_manager.create_worktree.assert_not_called()

    def test_build_context_prompt_prepends_warning(self):
        """Test build_context_prompt prepends CRITICAL: Worktree Context warning."""
        mock_git_manager = MagicMock()
        mock_worktree_storage = MagicMock()

        handler = WorktreeIsolationHandler(
            git_manager=mock_git_manager,
            worktree_storage=mock_worktree_storage,
        )

        original_prompt = "Please implement the login feature."
        ctx = IsolationContext(
            cwd="/tmp/worktrees/feature-branch",
            branch_name="feature-branch",
            worktree_id="wt-123",
            isolation_type="worktree",
            extra={"main_repo_path": "/path/to/main/repo"},
        )

        result = handler.build_context_prompt(original_prompt, ctx)

        assert "CRITICAL: Worktree Context" in result
        assert original_prompt in result
        assert "feature-branch" in result

    def test_is_isolation_handler_subclass(self):
        """Test WorktreeIsolationHandler is a subclass of IsolationHandler."""
        assert issubclass(WorktreeIsolationHandler, IsolationHandler)


class TestCloneIsolationHandler:
    """Tests for CloneIsolationHandler."""

    @pytest.mark.asyncio
    async def test_prepare_environment_creates_clone(self):
        """Test prepare_environment creates shallow clone if not exists."""
        mock_clone_manager = MagicMock()
        mock_clone_manager.create_clone.return_value = MagicMock(
            success=True,
            clone_path="/tmp/clones/my-branch",
        )

        mock_clone_storage = MagicMock()
        mock_clone_storage.get_by_branch.return_value = None  # No existing clone
        mock_clone_storage.create.return_value = MagicMock(
            id="clone-123",
            clone_path="/tmp/clones/my-branch",
            branch_name="my-branch",
        )

        handler = CloneIsolationHandler(
            clone_manager=mock_clone_manager,
            clone_storage=mock_clone_storage,
        )

        config = SpawnConfig(
            prompt="Test",
            task_id=None,
            task_title=None,
            task_seq_num=None,
            branch_name="my-branch",
            branch_prefix=None,
            base_branch="main",
            project_id="proj-123",
            project_path="/path/to/main/repo",
            provider="claude",
            parent_session_id="sess-456",
        )

        ctx = await handler.prepare_environment(config)

        assert ctx.isolation_type == "clone"
        assert ctx.clone_id == "clone-123"
        assert ctx.branch_name == "my-branch"
        mock_clone_manager.create_clone.assert_called_once()

    @pytest.mark.asyncio
    async def test_prepare_environment_reuses_existing_clone(self):
        """Test prepare_environment reuses existing clone for same branch."""
        mock_clone_manager = MagicMock()

        mock_clone_storage = MagicMock()
        mock_clone_storage.get_by_branch.return_value = MagicMock(
            id="existing-clone-456",
            clone_path="/tmp/clones/existing-branch",
            branch_name="existing-branch",
        )

        handler = CloneIsolationHandler(
            clone_manager=mock_clone_manager,
            clone_storage=mock_clone_storage,
        )

        config = SpawnConfig(
            prompt="Test",
            task_id=None,
            task_title=None,
            task_seq_num=None,
            branch_name="existing-branch",
            branch_prefix=None,
            base_branch="main",
            project_id="proj-123",
            project_path="/path/to/main/repo",
            provider="claude",
            parent_session_id="sess-456",
        )

        ctx = await handler.prepare_environment(config)

        assert ctx.clone_id == "existing-clone-456"
        assert ctx.cwd == "/tmp/clones/existing-branch"
        # Should NOT create a new clone
        mock_clone_manager.create_clone.assert_not_called()

    def test_build_context_prompt_prepends_warning(self):
        """Test build_context_prompt prepends CRITICAL: Clone Context warning."""
        mock_clone_manager = MagicMock()
        mock_clone_storage = MagicMock()

        handler = CloneIsolationHandler(
            clone_manager=mock_clone_manager,
            clone_storage=mock_clone_storage,
        )

        original_prompt = "Please implement the login feature."
        ctx = IsolationContext(
            cwd="/tmp/clones/feature-branch",
            branch_name="feature-branch",
            clone_id="clone-123",
            isolation_type="clone",
            extra={"source_repo": "https://github.com/user/repo.git"},
        )

        result = handler.build_context_prompt(original_prompt, ctx)

        assert "CRITICAL: Clone Context" in result
        assert original_prompt in result
        assert "feature-branch" in result

    def test_is_isolation_handler_subclass(self):
        """Test CloneIsolationHandler is a subclass of IsolationHandler."""
        assert issubclass(CloneIsolationHandler, IsolationHandler)


class TestGetIsolationHandler:
    """Tests for get_isolation_handler factory function."""

    def test_get_isolation_handler_current(self):
        """Test get_isolation_handler('current') returns CurrentIsolationHandler."""
        handler = get_isolation_handler("current")

        assert isinstance(handler, CurrentIsolationHandler)

    def test_get_isolation_handler_worktree(self):
        """Test get_isolation_handler('worktree', ...) returns WorktreeIsolationHandler."""
        mock_git_manager = MagicMock()
        mock_worktree_storage = MagicMock()

        handler = get_isolation_handler(
            "worktree",
            git_manager=mock_git_manager,
            worktree_storage=mock_worktree_storage,
        )

        assert isinstance(handler, WorktreeIsolationHandler)

    def test_get_isolation_handler_clone(self):
        """Test get_isolation_handler('clone', ...) returns CloneIsolationHandler."""
        mock_clone_manager = MagicMock()
        mock_clone_storage = MagicMock()

        handler = get_isolation_handler(
            "clone",
            clone_manager=mock_clone_manager,
            clone_storage=mock_clone_storage,
        )

        assert isinstance(handler, CloneIsolationHandler)

    def test_get_isolation_handler_invalid_mode_raises(self):
        """Test get_isolation_handler raises ValueError for invalid mode."""
        with pytest.raises(ValueError, match="Unknown isolation mode"):
            get_isolation_handler("invalid")

    def test_get_isolation_handler_worktree_missing_deps_raises(self):
        """Test get_isolation_handler('worktree') raises if dependencies missing."""
        with pytest.raises(ValueError, match="git_manager.*required"):
            get_isolation_handler("worktree")

    def test_get_isolation_handler_clone_missing_deps_raises(self):
        """Test get_isolation_handler('clone') raises if dependencies missing."""
        with pytest.raises(ValueError, match="clone_manager.*required"):
            get_isolation_handler("clone")
