import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.worktrees.merge.resolver import MergeResolver

pytestmark = pytest.mark.unit

@pytest.fixture
def mock_llm_service():
    """Mock for LLMService."""
    return MagicMock()


@pytest.fixture
def resolver(mock_llm_service):
    """MergeResolver instance with mocked LLM service."""
    res = MergeResolver()
    res._llm_service = mock_llm_service
    return res


@pytest.mark.asyncio
async def test_git_merge_success(resolver):
    """Test git merge with no conflicts."""
    # Mock subprocess execution
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"", b"")
        mock_exec.return_value = mock_process

        result = await resolver._git_merge("/tmp/repo", "feature", "main")

        assert result["success"] is True
        assert result["conflicts"] == []

        # Verify git merge called with expected args
        mock_exec.assert_called_with(
            "git",
            "merge",
            "--no-commit",
            "--no-ff",
            "feature",
            cwd="/tmp/repo",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )


@pytest.mark.asyncio
async def test_git_merge_conflict(resolver):
    """Test git merge with conflicts."""
    # Mock git merge failing (conflict)
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # 1. git merge fails
        mock_process_merge = AsyncMock()
        mock_process_merge.returncode = 1
        mock_process_merge.communicate.return_value = (
            b"CONFLICT (content): Merge conflict in file.txt",
            b"",
        )

        # 2. git diff finds conflicted files
        mock_process_diff = AsyncMock()
        mock_process_diff.returncode = 0
        mock_process_diff.communicate.return_value = (b"file.txt\n", b"")

        mock_exec.side_effect = [mock_process_merge, mock_process_diff]

        # Mock reading file content with conflicts
        with patch.object(
            Path,
            "read_text",
            return_value="<<<<<<< HEAD\nA\n=======\nB\n>>>>>>> feature\n",
        ):
            result = await resolver._git_merge("/tmp/repo", "feature", "main")

            assert result["success"] is False
            assert len(result["conflicts"]) == 1
            assert result["conflicts"][0]["file"] == "file.txt"
            assert len(result["conflicts"][0]["hunks"]) == 1


@pytest.mark.asyncio
async def test_resolve_conflicts_only_success(resolver, mock_llm_service):
    """Test conflict-only resolution success."""
    conflicts = [
        {
            "file": "file.txt",
            "hunks": [{"ours": "A", "theirs": "B", "start_line": 1, "end_line": 3}],
        }
    ]

    # Mock LLM response
    mock_provider = MagicMock()
    mock_provider.generate_text = AsyncMock(return_value="<code>RESOLVED CONTENT</code>")
    mock_llm_service.get_default_provider.return_value = mock_provider

    result = await resolver._resolve_conflicts_only(conflicts)

    assert result["success"] is True
    # Implementation stores full response currently
    assert result["resolutions"][0]["content"] == "<code>RESOLVED CONTENT</code>"


@pytest.mark.asyncio
async def test_resolve_conflicts_only_failure(resolver, mock_llm_service):
    """Test conflict-only resolution failure."""
    conflicts = [{"file": "file.txt", "hunks": [{"ours": "A", "theirs": "B"}]}]

    # Mock LLM failure or empty response
    mock_provider = MagicMock()
    mock_provider.generate_text = AsyncMock(return_value=None)
    mock_llm_service.get_default_provider.return_value = mock_provider

    result = await resolver._resolve_conflicts_only(conflicts)
    assert result["success"] is False


@pytest.mark.asyncio
async def test_resolve_full_file(resolver, mock_llm_service):
    """Test full-file resolution."""
    conflicts = [{"file": "file.txt", "hunks": []}]

    # Mock reading full file
    with patch.object(Path, "read_text", return_value="FULL FILE CONTENT"):
        mock_provider = MagicMock()
        mock_provider.generate_text = AsyncMock(return_value="FIXED CONTENT")
        mock_llm_service.get_default_provider.return_value = mock_provider

        result = await resolver._resolve_full_file(conflicts)

        assert result["success"] is True
        assert len(result["resolutions"]) == 1
        assert result["resolutions"][0]["content"] == "FIXED CONTENT"
