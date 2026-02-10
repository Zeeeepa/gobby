"""Tests for memory HTTP REST routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gobby.servers.routes.memory import create_memory_router
from gobby.storage.memories import Memory

pytestmark = pytest.mark.unit

NOW_ISO = "2026-02-10T12:00:00+00:00"


def _make_memory(**overrides) -> Memory:
    """Create a Memory with defaults."""
    defaults = {
        "id": "mm-abc123",
        "memory_type": "fact",
        "content": "User prefers dark mode",
        "created_at": NOW_ISO,
        "updated_at": NOW_ISO,
        "project_id": "test-project",
        "source_type": "user",
        "source_session_id": None,
        "importance": 0.8,
        "access_count": 3,
        "last_accessed_at": NOW_ISO,
        "tags": ["ui", "preference"],
    }
    defaults.update(overrides)
    return Memory(**defaults)


@pytest.fixture
def mock_server():
    """Create mock HTTPServer with memory_manager."""
    server = MagicMock()
    server.memory_manager = MagicMock()
    return server


@pytest.fixture
def client(mock_server):
    """Create TestClient with memory router."""
    app = FastAPI()
    router = create_memory_router(mock_server)
    app.include_router(router)
    return TestClient(app)


# =============================================================================
# GET /memories - list
# =============================================================================


class TestListMemories:
    """Test GET /memories endpoint."""

    def test_list_returns_memories(self, client, mock_server) -> None:
        """GET /memories returns a list of memories."""
        mock_server.memory_manager.list_memories.return_value = [
            _make_memory(id="mm-1", content="Memory one"),
            _make_memory(id="mm-2", content="Memory two"),
        ]
        response = client.get("/memories")
        assert response.status_code == 200
        data = response.json()
        assert len(data["memories"]) == 2
        assert data["memories"][0]["id"] == "mm-1"

    def test_list_with_filters(self, client, mock_server) -> None:
        """GET /memories supports query parameter filters."""
        mock_server.memory_manager.list_memories.return_value = []
        response = client.get(
            "/memories",
            params={
                "project_id": "proj-1",
                "memory_type": "fact",
                "min_importance": 0.5,
                "limit": 20,
            },
        )
        assert response.status_code == 200
        mock_server.memory_manager.list_memories.assert_called_once_with(
            project_id="proj-1",
            memory_type="fact",
            min_importance=0.5,
            limit=20,
            offset=0,
        )

    def test_list_empty(self, client, mock_server) -> None:
        """GET /memories returns empty list when no memories."""
        mock_server.memory_manager.list_memories.return_value = []
        response = client.get("/memories")
        assert response.status_code == 200
        assert response.json()["memories"] == []


# =============================================================================
# POST /memories - create
# =============================================================================


class TestCreateMemory:
    """Test POST /memories endpoint."""

    def test_create_memory(self, client, mock_server) -> None:
        """POST /memories creates a memory and returns id."""
        mock_server.memory_manager.remember = AsyncMock(
            return_value=_make_memory(id="mm-new-123")
        )
        response = client.post(
            "/memories",
            json={
                "content": "User prefers dark mode",
                "memory_type": "preference",
                "importance": 0.9,
                "project_id": "test-project",
                "tags": ["ui"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "mm-new-123"
        assert data["content"] == "User prefers dark mode"

    def test_create_requires_content(self, client, mock_server) -> None:
        """POST /memories requires content field."""
        response = client.post("/memories", json={})
        assert response.status_code == 422


# =============================================================================
# GET /memories/{id} - detail
# =============================================================================


class TestGetMemory:
    """Test GET /memories/{id} endpoint."""

    def test_get_memory(self, client, mock_server) -> None:
        """GET /memories/{id} returns memory detail."""
        mock_server.memory_manager.get_memory.return_value = _make_memory()
        response = client.get("/memories/mm-abc123")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "mm-abc123"
        assert data["content"] == "User prefers dark mode"
        assert data["tags"] == ["ui", "preference"]

    def test_get_memory_not_found(self, client, mock_server) -> None:
        """GET /memories/{id} returns 404 when not found."""
        mock_server.memory_manager.get_memory.return_value = None
        response = client.get("/memories/nonexistent")
        assert response.status_code == 404


# =============================================================================
# PUT /memories/{id} - update
# =============================================================================


class TestUpdateMemory:
    """Test PUT /memories/{id} endpoint."""

    def test_update_memory(self, client, mock_server) -> None:
        """PUT /memories/{id} updates and returns memory."""
        mock_server.memory_manager.update_memory.return_value = _make_memory(
            content="Updated content", importance=0.95
        )
        response = client.put(
            "/memories/mm-abc123",
            json={"content": "Updated content", "importance": 0.95},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Updated content"
        assert data["importance"] == 0.95

    def test_update_not_found(self, client, mock_server) -> None:
        """PUT /memories/{id} returns 404 when not found."""
        mock_server.memory_manager.update_memory.side_effect = ValueError(
            "Memory not found"
        )
        response = client.put(
            "/memories/nonexistent", json={"content": "new content"}
        )
        assert response.status_code == 404


# =============================================================================
# DELETE /memories/{id} - delete
# =============================================================================


class TestDeleteMemory:
    """Test DELETE /memories/{id} endpoint."""

    def test_delete_memory(self, client, mock_server) -> None:
        """DELETE /memories/{id} removes memory."""
        mock_server.memory_manager.forget.return_value = True
        response = client.delete("/memories/mm-abc123")
        assert response.status_code == 200
        assert response.json()["deleted"] is True
        mock_server.memory_manager.forget.assert_called_once_with("mm-abc123")

    def test_delete_not_found(self, client, mock_server) -> None:
        """DELETE /memories/{id} returns 404 when not found."""
        mock_server.memory_manager.forget.return_value = False
        response = client.delete("/memories/nonexistent")
        assert response.status_code == 404


# =============================================================================
# GET /memories/search - search
# =============================================================================


class TestSearchMemories:
    """Test GET /memories/search endpoint."""

    def test_search_returns_results(self, client, mock_server) -> None:
        """GET /memories/search?q=query returns ranked results."""
        mock_server.memory_manager.recall.return_value = [
            _make_memory(id="mm-1", content="Dark mode preference"),
        ]
        response = client.get("/memories/search", params={"q": "dark mode"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["id"] == "mm-1"
        assert data["query"] == "dark mode"

    def test_search_requires_query(self, client, mock_server) -> None:
        """GET /memories/search requires q parameter."""
        response = client.get("/memories/search")
        assert response.status_code == 422

    def test_search_with_filters(self, client, mock_server) -> None:
        """GET /memories/search supports project_id and limit filters."""
        mock_server.memory_manager.recall.return_value = []
        response = client.get(
            "/memories/search",
            params={"q": "test", "project_id": "proj-1", "limit": 5},
        )
        assert response.status_code == 200
        mock_server.memory_manager.recall.assert_called_once_with(
            query="test",
            project_id="proj-1",
            limit=5,
            min_importance=0.0,
        )


# =============================================================================
# GET /memories/stats - statistics
# =============================================================================


class TestMemoryStats:
    """Test GET /memories/stats endpoint."""

    def test_stats_returns_counts(self, client, mock_server) -> None:
        """GET /memories/stats returns memory statistics."""
        mock_server.memory_manager.get_stats.return_value = {
            "total_count": 42,
            "by_type": {"fact": 30, "preference": 12},
            "avg_importance": 0.65,
            "project_id": None,
        }
        response = client.get("/memories/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 42
        assert data["by_type"]["fact"] == 30
        assert data["avg_importance"] == 0.65

    def test_stats_with_project_filter(self, client, mock_server) -> None:
        """GET /memories/stats supports project_id filter."""
        mock_server.memory_manager.get_stats.return_value = {
            "total_count": 10,
            "by_type": {"fact": 10},
            "avg_importance": 0.7,
            "project_id": "proj-1",
        }
        response = client.get("/memories/stats", params={"project_id": "proj-1"})
        assert response.status_code == 200
        mock_server.memory_manager.get_stats.assert_called_once_with(
            project_id="proj-1"
        )
