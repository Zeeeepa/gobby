"""Tests for artifacts MCP tool registry."""

import asyncio
from unittest.mock import MagicMock

import pytest

from gobby.mcp_proxy.tools.artifacts import create_artifacts_registry

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_artifact_manager():
    """Create a mock artifact manager."""
    manager = MagicMock()
    manager.search_artifacts.return_value = []
    manager.list_artifacts.return_value = []
    manager.get_artifact.return_value = None
    return manager


@pytest.fixture
def artifacts_registry(mock_artifact_manager):
    """Create artifacts registry with mock manager."""
    return create_artifacts_registry(artifact_manager=mock_artifact_manager)


def call_tool(registry, name: str, **kwargs):
    """Helper to call a tool synchronously."""
    return asyncio.run(registry.call(name, kwargs))


class TestSearchArtifacts:
    """Tests for search_artifacts tool."""

    def test_empty_query_returns_empty(self, artifacts_registry) -> None:
        """Test that empty query returns empty result."""
        result = call_tool(artifacts_registry, "search_artifacts", query="")
        assert "error" not in result
        assert result["artifacts"] == []
        assert result["count"] == 0

    def test_whitespace_query_returns_empty(self, artifacts_registry) -> None:
        """Test that whitespace-only query returns empty result."""
        result = call_tool(artifacts_registry, "search_artifacts", query="   ")
        assert "error" not in result
        assert result["artifacts"] == []
        assert result["count"] == 0

    def test_valid_query_calls_manager(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test that valid query calls artifact manager."""
        call_tool(artifacts_registry, "search_artifacts", query="test query")
        mock_artifact_manager.search_artifacts.assert_called_once_with(
            query_text="test query",
            session_id=None,
            artifact_type=None,
            limit=50,
        )

    def test_search_with_filters(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test search with session_id and type filters."""
        call_tool(
            artifacts_registry,
            "search_artifacts",
            query="test",
            session_id="sess-123",
            artifact_type="code",
            limit=10,
        )
        mock_artifact_manager.search_artifacts.assert_called_once_with(
            query_text="test",
            session_id="sess-123",
            artifact_type="code",
            limit=10,
        )

    def test_search_exception_handling(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test that exceptions are handled gracefully."""
        mock_artifact_manager.search_artifacts.side_effect = Exception("DB error")
        result = call_tool(artifacts_registry, "search_artifacts", query="test")
        assert "error" in result
        assert "DB error" in result["error"]
        assert result["artifacts"] == []


class TestGetArtifact:
    """Tests for get_artifact tool."""

    def test_nonexistent_artifact_returns_error(
        self, artifacts_registry, mock_artifact_manager
    ) -> None:
        """Test that non-existent artifact returns error."""
        mock_artifact_manager.get_artifact.return_value = None
        result = call_tool(artifacts_registry, "get_artifact", artifact_id="nonexistent-id")
        assert "error" in result
        assert "not found" in result["error"]
        assert result["artifact"] is None

    def test_existing_artifact_returns_data(
        self, artifacts_registry, mock_artifact_manager
    ) -> None:
        """Test that existing artifact is returned."""
        mock_artifact = MagicMock()
        mock_artifact.to_dict.return_value = {"id": "art-123", "content": "test"}
        mock_artifact_manager.get_artifact.return_value = mock_artifact

        result = call_tool(artifacts_registry, "get_artifact", artifact_id="art-123")
        assert "error" not in result
        assert result["artifact"]["id"] == "art-123"

    def test_get_artifact_exception_handling(
        self, artifacts_registry, mock_artifact_manager
    ) -> None:
        """Test that exceptions are handled gracefully."""
        mock_artifact_manager.get_artifact.side_effect = Exception("DB error")
        result = call_tool(artifacts_registry, "get_artifact", artifact_id="test-id")
        assert "error" in result
        assert "DB error" in result["error"]


class TestGetTimeline:
    """Tests for get_timeline tool."""

    def test_missing_session_id_returns_error(self, artifacts_registry) -> None:
        """Test that missing session_id returns error."""
        result = call_tool(artifacts_registry, "get_timeline", session_id=None)
        assert "error" in result
        assert "session_id is required" in result["error"]
        assert result["artifacts"] == []

    def test_empty_session_id_returns_error(self, artifacts_registry) -> None:
        """Test that empty session_id returns error."""
        result = call_tool(artifacts_registry, "get_timeline", session_id="")
        assert "error" in result
        assert "session_id is required" in result["error"]

    def test_valid_session_returns_timeline(
        self, artifacts_registry, mock_artifact_manager
    ) -> None:
        """Test that valid session_id returns timeline."""
        mock_artifact = MagicMock()
        mock_artifact.to_dict.return_value = {"id": "art-1", "created_at": "2024-01-01"}
        mock_artifact_manager.list_artifacts.return_value = [mock_artifact]

        result = call_tool(artifacts_registry, "get_timeline", session_id="sess-123")
        assert "error" not in result
        assert result["count"] == 1
        mock_artifact_manager.list_artifacts.assert_called_once()

    def test_timeline_exception_handling(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test that exceptions are handled gracefully."""
        mock_artifact_manager.list_artifacts.side_effect = Exception("DB error")
        result = call_tool(artifacts_registry, "get_timeline", session_id="sess-123")
        assert "error" in result
        assert "DB error" in result["error"]


class TestListArtifacts:
    """Tests for list_artifacts tool."""

    def test_list_with_no_filters(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test listing artifacts without filters."""
        call_tool(artifacts_registry, "list_artifacts")
        mock_artifact_manager.list_artifacts.assert_called_once_with(
            session_id=None,
            artifact_type=None,
            limit=100,
            offset=0,
        )

    def test_list_with_filters(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test listing artifacts with filters."""
        call_tool(
            artifacts_registry,
            "list_artifacts",
            session_id="sess-123",
            artifact_type="diff",
            limit=50,
            offset=10,
        )
        mock_artifact_manager.list_artifacts.assert_called_once_with(
            session_id="sess-123",
            artifact_type="diff",
            limit=50,
            offset=10,
        )

    def test_list_exception_handling(self, artifacts_registry, mock_artifact_manager) -> None:
        """Test that exceptions are handled gracefully."""
        mock_artifact_manager.list_artifacts.side_effect = Exception("DB error")
        result = call_tool(artifacts_registry, "list_artifacts")
        assert "error" in result
        assert "DB error" in result["error"]


class TestCreateArtifactsRegistry:
    """Tests for registry creation."""

    def test_creates_registry_with_manager(self, mock_artifact_manager) -> None:
        """Test that registry is created with provided manager."""
        registry = create_artifacts_registry(artifact_manager=mock_artifact_manager)
        assert registry.name == "gobby-artifacts"

    def test_registry_has_all_tools(self, artifacts_registry) -> None:
        """Test that registry has all expected tools."""
        tools = artifacts_registry.list_tools()
        tool_names = [t["name"] for t in tools]
        assert "search_artifacts" in tool_names
        assert "list_artifacts" in tool_names
        assert "get_artifact" in tool_names
        assert "get_timeline" in tool_names
