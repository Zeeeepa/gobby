"""Tests for merge_worktree tool in _sync.py — worktree_path returns and auto-resolve."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_git_result(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    """Create a mock git subprocess result."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _make_registry_context(
    worktree_path: str = "/tmp/wt", branch: str = "feat", base: str = "main"
):
    """Create a mock RegistryContext with worktree storage and git manager."""
    ctx = MagicMock()
    wt = MagicMock()
    wt.worktree_path = worktree_path
    wt.branch_name = branch
    wt.base_branch = base
    ctx.worktree_storage.get.return_value = wt
    ctx.git_manager = MagicMock()
    ctx.project_id = "test-project"
    return ctx


@pytest.mark.asyncio
async def test_merge_worktree_success_returns_worktree_path():
    """Successful merge returns worktree_path."""
    from gobby.mcp_proxy.tools.worktrees._sync import create_sync_registry

    ctx = _make_registry_context()

    # fetch succeeds, merge succeeds
    ctx.git_manager._run_git.side_effect = [
        _make_git_result(0),  # fetch
        _make_git_result(0),  # merge
    ]

    registry = create_sync_registry(ctx)
    merge_tool = registry.get_tool("merge_worktree")

    with patch(
        "gobby.mcp_proxy.tools.worktrees._sync.resolve_project_context",
        return_value=(ctx.git_manager, "test-project", None),
    ):
        result = await merge_tool("wt-123")

    assert result["success"] is True
    assert result["worktree_path"] == "/tmp/wt"


@pytest.mark.asyncio
async def test_merge_worktree_conflict_returns_worktree_path():
    """Merge with conflicts returns worktree_path."""
    from gobby.mcp_proxy.tools.worktrees._sync import create_sync_registry

    ctx = _make_registry_context()

    # fetch succeeds, merge fails, diff shows conflict, merge --abort succeeds
    ctx.git_manager._run_git.side_effect = [
        _make_git_result(0),  # fetch
        _make_git_result(1, stderr="CONFLICT"),  # merge fails
        _make_git_result(0, stdout="src/main.py\n"),  # diff --name-only
        _make_git_result(0),  # merge --abort
    ]

    registry = create_sync_registry(ctx)
    merge_tool = registry.get_tool("merge_worktree")

    with (
        patch(
            "gobby.mcp_proxy.tools.worktrees._sync.resolve_project_context",
            return_value=(ctx.git_manager, "test-project", None),
        ),
        patch(
            "gobby.worktrees.merge.resolver.auto_resolve_trivial_conflicts",
            new_callable=AsyncMock,
            return_value=["src/main.py"],
        ),
    ):
        result = await merge_tool("wt-123")

    assert result["success"] is False
    assert result["has_conflicts"] is True
    assert result["worktree_path"] == "/tmp/wt"


@pytest.mark.asyncio
async def test_merge_worktree_auto_resolves_trivial_conflicts():
    """Merge auto-resolves .gobby/*.jsonl and succeeds when no real conflicts remain."""
    from gobby.mcp_proxy.tools.worktrees._sync import create_sync_registry

    ctx = _make_registry_context()

    # fetch, merge fails, diff shows only trivial files, commit succeeds
    ctx.git_manager._run_git.side_effect = [
        _make_git_result(0),  # fetch
        _make_git_result(1, stderr="CONFLICT"),  # merge fails
        _make_git_result(0, stdout=".gobby/tasks.jsonl\n"),  # diff --name-only
        _make_git_result(0),  # commit --no-edit
    ]

    registry = create_sync_registry(ctx)
    merge_tool = registry.get_tool("merge_worktree")

    with (
        patch(
            "gobby.mcp_proxy.tools.worktrees._sync.resolve_project_context",
            return_value=(ctx.git_manager, "test-project", None),
        ),
        patch(
            "gobby.worktrees.merge.resolver.auto_resolve_trivial_conflicts",
            new_callable=AsyncMock,
            return_value=[],  # all trivial, nothing remaining
        ),
    ):
        result = await merge_tool("wt-123")

    assert result["success"] is True
    assert "auto-resolved" in result["message"]
    assert result["worktree_path"] == "/tmp/wt"
    assert result["auto_resolved"] == [".gobby/tasks.jsonl"]


@pytest.mark.asyncio
async def test_merge_worktree_push_failure_returns_worktree_path():
    """Push failure returns worktree_path."""
    from gobby.mcp_proxy.tools.worktrees._sync import create_sync_registry

    ctx = _make_registry_context()

    # fetch, merge succeeds, push fails
    ctx.git_manager._run_git.side_effect = [
        _make_git_result(0),  # fetch
        _make_git_result(0),  # merge
        _make_git_result(1, stderr="rejected"),  # push fails
    ]

    registry = create_sync_registry(ctx)
    merge_tool = registry.get_tool("merge_worktree")

    with patch(
        "gobby.mcp_proxy.tools.worktrees._sync.resolve_project_context",
        return_value=(ctx.git_manager, "test-project", None),
    ):
        result = await merge_tool("wt-123", push=True)

    assert result["success"] is False
    assert result["worktree_path"] == "/tmp/wt"
    assert result["merge_succeeded"] is True


@pytest.mark.asyncio
async def test_merge_worktree_non_conflict_error_returns_worktree_path():
    """Non-conflict merge error returns worktree_path."""
    from gobby.mcp_proxy.tools.worktrees._sync import create_sync_registry

    ctx = _make_registry_context()

    # fetch, merge fails with no conflicts
    ctx.git_manager._run_git.side_effect = [
        _make_git_result(0),  # fetch
        _make_git_result(128, stdout="fatal: not a git repo", stderr=""),  # merge fails
        _make_git_result(0, stdout=""),  # diff --name-only (no conflicts)
    ]

    registry = create_sync_registry(ctx)
    merge_tool = registry.get_tool("merge_worktree")

    with patch(
        "gobby.mcp_proxy.tools.worktrees._sync.resolve_project_context",
        return_value=(ctx.git_manager, "test-project", None),
    ):
        result = await merge_tool("wt-123")

    assert result["success"] is False
    assert result["has_conflicts"] is False
    assert result["worktree_path"] == "/tmp/wt"
