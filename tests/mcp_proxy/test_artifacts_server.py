"""Tests for gobby-artifacts MCP server tools.

These tests define the expected behavior for the artifacts MCP server.
Tests should fail initially (TDD red phase) until the implementation is complete.

The gobby-artifacts server should expose:
- search_artifacts: Full-text search across artifact content
- list_artifacts: List artifacts with session_id and type filters
- get_artifact: Get a single artifact by ID
- get_timeline: Get artifacts for a session in chronological order
"""

from unittest.mock import MagicMock

import pytest


# Mock the module since it doesn't exist yet
# Once implemented, these can be replaced with actual imports
def get_artifacts_registry():
    """Import the artifacts registry when it exists."""
    try:
        from gobby.mcp_proxy.tools.artifacts import create_artifacts_registry

        return create_artifacts_registry
    except ImportError:
        pytest.skip("gobby-artifacts MCP server not yet implemented")


class TestSearchArtifacts:
    """Tests for the search_artifacts tool."""

    def test_search_by_query_returns_matching_artifacts(self):
        """Verify search_artifacts finds artifacts matching query text."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()
        mock_artifact_manager.search_artifacts.return_value = [
            MagicMock(
                id="art-123",
                session_id="sess-456",
                artifact_type="code",
                content="function calculateTotal(items) { ... }",
                created_at="2024-01-01T00:00:00Z",
                metadata=None,
                source_file="utils.js",
                line_start=10,
                line_end=25,
                to_dict=lambda: {
                    "id": "art-123",
                    "artifact_type": "code",
                    "content": "function calculateTotal...",
                },
            )
        ]

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("search_artifacts")
        assert tool is not None, "search_artifacts tool should exist"

        result = tool.func(query="calculateTotal")

        assert result["success"] is True
        assert len(result["artifacts"]) == 1
        assert result["artifacts"][0]["id"] == "art-123"
        mock_artifact_manager.search_artifacts.assert_called_once()

    def test_search_with_session_filter(self):
        """Verify search_artifacts can filter by session_id."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()
        mock_artifact_manager.search_artifacts.return_value = []

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("search_artifacts")

        result = tool.func(query="test", session_id="sess-123")

        mock_artifact_manager.search_artifacts.assert_called_once_with(
            query_text="test",
            session_id="sess-123",
            artifact_type=None,
            limit=50,
        )

    def test_search_with_type_filter(self):
        """Verify search_artifacts can filter by artifact_type."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()
        mock_artifact_manager.search_artifacts.return_value = []

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("search_artifacts")

        result = tool.func(query="error", artifact_type="error")

        mock_artifact_manager.search_artifacts.assert_called_once_with(
            query_text="error",
            session_id=None,
            artifact_type="error",
            limit=50,
        )

    def test_search_empty_query_returns_empty(self):
        """Verify empty query returns empty results."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()
        mock_artifact_manager.search_artifacts.return_value = []

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("search_artifacts")

        result = tool.func(query="")

        assert result["success"] is True
        assert result["artifacts"] == []


class TestListArtifacts:
    """Tests for the list_artifacts tool."""

    def test_list_all_artifacts(self):
        """Verify list_artifacts returns all artifacts when no filters."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()
        mock_artifact_manager.list_artifacts.return_value = [
            MagicMock(
                id="art-1",
                to_dict=lambda: {"id": "art-1", "artifact_type": "code"},
            ),
            MagicMock(
                id="art-2",
                to_dict=lambda: {"id": "art-2", "artifact_type": "diff"},
            ),
        ]

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("list_artifacts")
        assert tool is not None, "list_artifacts tool should exist"

        result = tool.func()

        assert result["success"] is True
        assert len(result["artifacts"]) == 2

    def test_list_artifacts_by_session(self):
        """Verify list_artifacts filters by session_id."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()
        mock_artifact_manager.list_artifacts.return_value = []

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("list_artifacts")

        result = tool.func(session_id="sess-123")

        mock_artifact_manager.list_artifacts.assert_called_once()
        call_kwargs = mock_artifact_manager.list_artifacts.call_args
        assert call_kwargs[1].get("session_id") == "sess-123" or call_kwargs[0][0] == "sess-123"

    def test_list_artifacts_by_type(self):
        """Verify list_artifacts filters by artifact_type."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()
        mock_artifact_manager.list_artifacts.return_value = []

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("list_artifacts")

        result = tool.func(artifact_type="error")

        mock_artifact_manager.list_artifacts.assert_called_once()

    def test_list_artifacts_with_pagination(self):
        """Verify list_artifacts supports limit and offset."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()
        mock_artifact_manager.list_artifacts.return_value = []

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("list_artifacts")

        result = tool.func(limit=10, offset=20)

        call_args = mock_artifact_manager.list_artifacts.call_args
        # Check limit and offset were passed
        assert 10 in call_args[0] or call_args[1].get("limit") == 10
        assert 20 in call_args[0] or call_args[1].get("offset") == 20


class TestGetArtifact:
    """Tests for the get_artifact tool."""

    def test_get_existing_artifact(self):
        """Verify get_artifact returns artifact by ID."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()
        mock_artifact = MagicMock()
        mock_artifact.id = "art-123"
        mock_artifact.artifact_type = "code"
        mock_artifact.content = "const x = 1;"
        mock_artifact.to_dict.return_value = {
            "id": "art-123",
            "artifact_type": "code",
            "content": "const x = 1;",
        }
        mock_artifact_manager.get_artifact.return_value = mock_artifact

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("get_artifact")
        assert tool is not None, "get_artifact tool should exist"

        result = tool.func(artifact_id="art-123")

        assert result["success"] is True
        assert result["artifact"]["id"] == "art-123"
        mock_artifact_manager.get_artifact.assert_called_once_with("art-123")

    def test_get_nonexistent_artifact_returns_error(self):
        """Verify get_artifact returns error for invalid ID."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()
        mock_artifact_manager.get_artifact.return_value = None

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("get_artifact")

        result = tool.func(artifact_id="art-nonexistent")

        assert result["success"] is False
        assert "not found" in result["error"].lower()


class TestGetTimeline:
    """Tests for the get_timeline tool (artifacts chronologically)."""

    def test_timeline_returns_chronological_order(self):
        """Verify get_timeline returns artifacts in chronological order."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()

        # list_artifacts returns newest first by default, timeline reverses to oldest first
        mock_artifacts = [
            MagicMock(
                id="art-3",
                created_at="2024-01-01T02:00:00Z",
                to_dict=lambda: {"id": "art-3", "created_at": "2024-01-01T02:00:00Z"},
            ),
            MagicMock(
                id="art-2",
                created_at="2024-01-01T01:00:00Z",
                to_dict=lambda: {"id": "art-2", "created_at": "2024-01-01T01:00:00Z"},
            ),
            MagicMock(
                id="art-1",
                created_at="2024-01-01T00:00:00Z",
                to_dict=lambda: {"id": "art-1", "created_at": "2024-01-01T00:00:00Z"},
            ),
        ]
        mock_artifact_manager.list_artifacts.return_value = mock_artifacts

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("get_timeline")
        assert tool is not None, "get_timeline tool should exist"

        result = tool.func(session_id="sess-123")

        assert result["success"] is True
        assert len(result["artifacts"]) == 3
        # Should be ordered chronologically (oldest first)
        assert result["artifacts"][0]["id"] == "art-1"
        assert result["artifacts"][2]["id"] == "art-3"

    def test_timeline_requires_session_id(self):
        """Verify get_timeline requires session_id parameter."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("get_timeline")

        # Should return error without session_id
        result = tool.func()

        assert result["success"] is False
        assert "session_id" in result["error"].lower()

    def test_timeline_with_type_filter(self):
        """Verify get_timeline can filter by artifact_type."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()
        mock_artifact_manager.list_artifacts.return_value = []

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("get_timeline")

        result = tool.func(session_id="sess-123", artifact_type="code")

        assert result["success"] is True
        mock_artifact_manager.list_artifacts.assert_called_once()


class TestMCPResponseFormat:
    """Tests for proper MCP response format."""

    def test_search_returns_mcp_format(self):
        """Verify search_artifacts returns proper MCP format."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()
        mock_artifact_manager.search_artifacts.return_value = []

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("search_artifacts")

        result = tool.func(query="test")

        # Should have success flag
        assert "success" in result
        # Should have artifacts list
        assert "artifacts" in result
        assert isinstance(result["artifacts"], list)

    def test_list_returns_mcp_format(self):
        """Verify list_artifacts returns proper MCP format."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()
        mock_artifact_manager.list_artifacts.return_value = []

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("list_artifacts")

        result = tool.func()

        assert "success" in result
        assert "artifacts" in result
        assert isinstance(result["artifacts"], list)

    def test_get_returns_mcp_format(self):
        """Verify get_artifact returns proper MCP format."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()
        mock_artifact = MagicMock()
        mock_artifact.to_dict.return_value = {"id": "art-123"}
        mock_artifact_manager.get_artifact.return_value = mock_artifact

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("get_artifact")

        result = tool.func(artifact_id="art-123")

        assert "success" in result
        assert "artifact" in result
        assert isinstance(result["artifact"], dict)

    def test_error_response_format(self):
        """Verify error responses follow MCP format."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()
        mock_artifact_manager.get_artifact.return_value = None

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)
        tool = registry._tools.get("get_artifact")

        result = tool.func(artifact_id="nonexistent")

        assert result["success"] is False
        assert "error" in result
        assert isinstance(result["error"], str)


class TestRegistryStructure:
    """Tests for the registry structure and tool registration."""

    def test_registry_has_correct_name(self):
        """Verify registry is named gobby-artifacts."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)

        assert registry.name == "gobby-artifacts"

    def test_registry_has_all_required_tools(self):
        """Verify registry has all expected tools."""
        create_registry = get_artifacts_registry()

        mock_db = MagicMock()
        mock_artifact_manager = MagicMock()

        registry = create_registry(db=mock_db, artifact_manager=mock_artifact_manager)

        expected_tools = ["search_artifacts", "list_artifacts", "get_artifact", "get_timeline"]
        for tool_name in expected_tools:
            assert tool_name in registry._tools, f"Tool '{tool_name}' should be registered"
