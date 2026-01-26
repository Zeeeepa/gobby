"""
Tests for Isolation Handlers.

Tests the isolation abstraction layer for spawn_agent unified API.
"""

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.isolation import (
    CurrentIsolationHandler,
    IsolationContext,
    IsolationHandler,
    SpawnConfig,
    generate_branch_name,
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
