"""Tests for artifact write MCP tools: save, delete, tag, untag, list_by_task."""

from unittest.mock import MagicMock

import pytest

from gobby.mcp_proxy.tools.artifacts import create_artifacts_registry
from gobby.storage.artifact_classifier import ArtifactType

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
def mock_artifact_manager() -> MagicMock:
    """Create a mock artifact manager with write methods."""
    manager = MagicMock()
    manager.search_artifacts.return_value = []
    manager.list_artifacts.return_value = []
    manager.get_artifact.return_value = None
    manager.delete_artifact.return_value = True
    manager.add_tag.return_value = True
    manager.remove_tag.return_value = True
    manager.get_tags.return_value = []
    manager.list_by_tag.return_value = []
    return manager


@pytest.fixture
def artifacts_registry(mock_artifact_manager: MagicMock):
    """Create artifacts registry with mock manager."""
    return create_artifacts_registry(artifact_manager=mock_artifact_manager)


class TestSaveArtifact:
    """Tests for save_artifact tool."""

    async def test_save_with_required_params(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test save_artifact with required params creates artifact."""
        mock_artifact = MagicMock()
        mock_artifact.to_dict.return_value = {
            "id": "art-new",
            "content": "def hello(): pass",
            "artifact_type": "code",
        }
        mock_artifact_manager.create_artifact.return_value = mock_artifact

        result = await artifacts_registry.call(
            "save_artifact",
            {"content": "def hello(): pass", "session_id": "sess-123"},
        )

        assert result["success"] is True
        assert result["artifact"]["id"] == "art-new"
        mock_artifact_manager.create_artifact.assert_called_once()

    async def test_save_with_all_optional_params(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test save_artifact with all optional params."""
        mock_artifact = MagicMock()
        mock_artifact.to_dict.return_value = {"id": "art-full"}
        mock_artifact_manager.create_artifact.return_value = mock_artifact

        result = await artifacts_registry.call(
            "save_artifact",
            {
                "content": "import os",
                "session_id": "sess-123",
                "artifact_type": "code",
                "title": "OS import",
                "task_id": "task-001",
                "source_file": "main.py",
                "line_start": 1,
                "line_end": 1,
            },
        )

        assert result["success"] is True
        call_args = mock_artifact_manager.create_artifact.call_args
        assert call_args.kwargs["title"] == "OS import"
        assert call_args.kwargs["task_id"] == "task-001"
        assert call_args.kwargs["artifact_type"] == "code"

    async def test_save_auto_classifies_when_no_type(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test save_artifact auto-classifies when artifact_type not provided."""
        mock_artifact = MagicMock()
        mock_artifact.to_dict.return_value = {"id": "art-auto"}
        mock_artifact_manager.create_artifact.return_value = mock_artifact

        result = await artifacts_registry.call(
            "save_artifact",
            {"content": "def hello():\n    return 'world'", "session_id": "sess-123"},
        )

        assert result["success"] is True
        call_args = mock_artifact_manager.create_artifact.call_args
        # Should auto-classify as code (python detected)
        assert call_args.kwargs["artifact_type"] == ArtifactType.CODE.value

    async def test_save_exception_handling(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test save_artifact handles exceptions."""
        mock_artifact_manager.create_artifact.side_effect = Exception("DB error")
        result = await artifacts_registry.call(
            "save_artifact",
            {"content": "test", "session_id": "sess-123"},
        )
        assert result["success"] is False
        assert "DB error" in result["error"]


class TestDeleteArtifact:
    """Tests for delete_artifact tool."""

    async def test_delete_existing(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test delete_artifact removes existing artifact."""
        mock_artifact_manager.delete_artifact.return_value = True
        result = await artifacts_registry.call("delete_artifact", {"artifact_id": "art-123"})
        assert result["success"] is True
        mock_artifact_manager.delete_artifact.assert_called_once_with("art-123")

    async def test_delete_nonexistent(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test delete_artifact returns error for non-existent ID."""
        mock_artifact_manager.delete_artifact.return_value = False
        result = await artifacts_registry.call("delete_artifact", {"artifact_id": "nonexistent"})
        assert result["success"] is False
        assert "not found" in result["error"]


class TestTagArtifact:
    """Tests for tag_artifact and untag_artifact tools."""

    async def test_tag_artifact(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test tag_artifact adds tag."""
        result = await artifacts_registry.call(
            "tag_artifact", {"artifact_id": "art-123", "tag": "important"}
        )
        assert result["success"] is True
        mock_artifact_manager.add_tag.assert_called_once_with("art-123", "important")

    async def test_tag_artifact_idempotent(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test tag_artifact is idempotent."""
        mock_artifact_manager.add_tag.return_value = True
        result = await artifacts_registry.call(
            "tag_artifact", {"artifact_id": "art-123", "tag": "duplicate"}
        )
        assert result["success"] is True

    async def test_untag_artifact(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test untag_artifact removes tag."""
        mock_artifact_manager.remove_tag.return_value = True
        result = await artifacts_registry.call(
            "untag_artifact", {"artifact_id": "art-123", "tag": "old-tag"}
        )
        assert result["success"] is True

    async def test_untag_nonexistent(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test untag_artifact returns error for non-existent tag."""
        mock_artifact_manager.remove_tag.return_value = False
        result = await artifacts_registry.call(
            "untag_artifact", {"artifact_id": "art-123", "tag": "missing"}
        )
        assert result["success"] is False


class TestListArtifactsByTask:
    """Tests for list_artifacts_by_task tool."""

    async def test_list_by_task(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test list_artifacts_by_task returns artifacts for task."""
        mock_art = MagicMock()
        mock_art.to_dict.return_value = {"id": "art-1", "task_id": "task-001"}
        mock_artifact_manager.list_by_task.return_value = [mock_art]

        result = await artifacts_registry.call(
            "list_artifacts_by_task", {"task_id": "task-001"}
        )
        assert result["success"] is True
        assert result["count"] == 1

    async def test_list_by_task_with_type_filter(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test list_artifacts_by_task with artifact_type filter."""
        mock_artifact_manager.list_by_task.return_value = []
        result = await artifacts_registry.call(
            "list_artifacts_by_task",
            {"task_id": "task-001", "artifact_type": "code"},
        )
        assert result["success"] is True
        mock_artifact_manager.list_by_task.assert_called_once_with(
            task_id="task-001", artifact_type="code", limit=100
        )

    async def test_list_by_task_empty(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test list_artifacts_by_task with no matches."""
        mock_artifact_manager.list_by_task.return_value = []
        result = await artifacts_registry.call(
            "list_artifacts_by_task", {"task_id": "no-artifacts"}
        )
        assert result["success"] is True
        assert result["count"] == 0
        assert result["artifacts"] == []


class TestRegistryHasWriteTools:
    """Tests for registry tool listing including write tools."""

    async def test_registry_has_write_tools(self, artifacts_registry) -> None:
        """Test that registry has all write tools."""
        tools = artifacts_registry.list_tools()
        tool_names = [t["name"] for t in tools]
        assert "save_artifact" in tool_names
        assert "delete_artifact" in tool_names
        assert "tag_artifact" in tool_names
        assert "untag_artifact" in tool_names
        assert "list_artifacts_by_task" in tool_names
