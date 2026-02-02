"""Tests for HTTP pipeline endpoints."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from gobby.app_context import ServiceContainer
from gobby.servers.http import HTTPServer
from gobby.storage.database import LocalDatabase
from gobby.storage.sessions import LocalSessionManager

pytestmark = pytest.mark.unit


@pytest.fixture
def session_storage(temp_db: LocalDatabase) -> LocalSessionManager:
    """Create session storage."""
    return LocalSessionManager(temp_db)


@pytest.fixture
def mock_pipeline_executor():
    """Create a mock pipeline executor."""
    return MagicMock()


@pytest.fixture
def mock_workflow_loader():
    """Create a mock workflow loader."""
    return MagicMock()


@pytest.fixture
def http_server(
    session_storage: LocalSessionManager,
    mock_pipeline_executor,
    mock_workflow_loader,
) -> HTTPServer:
    """Create an HTTP server instance for testing."""
    services = ServiceContainer(
        config=None,
        database=session_storage.db,
        session_manager=session_storage,
        task_manager=MagicMock(),
        pipeline_executor=mock_pipeline_executor,
        workflow_loader=mock_workflow_loader,
    )
    return HTTPServer(
        services=services,
        port=60887,
        test_mode=True,
    )


@pytest.fixture
def client(http_server: HTTPServer) -> Iterator[TestClient]:
    """Create a test client for the HTTP server."""
    with patch("gobby.servers.http.HookManager") as MockHM:
        mock_instance = MockHM.return_value
        mock_instance._stop_registry = MagicMock()
        mock_instance.shutdown = MagicMock()
        with TestClient(http_server.app) as client:
            yield client


class TestPipelinesRunEndpoint:
    """Tests for POST /api/pipelines/run endpoint."""

    def test_run_pipeline_success(self, client, http_server) -> None:
        """Verify POST /api/pipelines/run returns 200 with execution details."""
        from gobby.workflows.definitions import PipelineDefinition, PipelineStep
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        # Setup mock loader
        mock_pipeline = PipelineDefinition(
            name="deploy",
            description="Deploy to production",
            steps=[PipelineStep(id="build", exec="npm run build")],
        )
        http_server.services.workflow_loader.load_pipeline.return_value = mock_pipeline

        # Setup mock executor
        mock_execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="deploy",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:01:00Z",
        )
        http_server.services.pipeline_executor.execute = AsyncMock(return_value=mock_execution)

        response = client.post(
            "/api/pipelines/run",
            json={"name": "deploy", "inputs": {"env": "prod"}, "project_id": "proj-1"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["execution_id"] == "pe-abc123"

    def test_run_pipeline_not_found(self, client, http_server) -> None:
        """Verify POST /api/pipelines/run returns 404 for unknown pipeline."""
        http_server.services.workflow_loader.load_pipeline.return_value = None

        response = client.post(
            "/api/pipelines/run",
            json={"name": "nonexistent", "inputs": {}},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_run_pipeline_approval_required(self, client, http_server) -> None:
        """Verify POST /api/pipelines/run returns 202 when approval is needed."""
        from gobby.workflows.definitions import PipelineDefinition, PipelineStep
        from gobby.workflows.pipeline_state import ApprovalRequired

        # Setup mock loader
        mock_pipeline = PipelineDefinition(
            name="deploy",
            description="Deploy to production",
            steps=[PipelineStep(id="build", exec="npm run build")],
        )
        http_server.services.workflow_loader.load_pipeline.return_value = mock_pipeline

        # Setup mock executor to raise ApprovalRequired
        http_server.services.pipeline_executor.execute = AsyncMock(
            side_effect=ApprovalRequired(
                execution_id="pe-abc123",
                step_id="deploy-step",
                token="approval-token-xyz",
                message="Manual approval required",
            )
        )

        response = client.post(
            "/api/pipelines/run",
            json={"name": "deploy", "inputs": {}},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "waiting_approval"
        assert data["token"] == "approval-token-xyz"
        assert data["execution_id"] == "pe-abc123"

    def test_run_pipeline_execution_error(self, client, http_server) -> None:
        """Verify POST /api/pipelines/run returns 500 on execution error."""
        from gobby.workflows.definitions import PipelineDefinition, PipelineStep

        # Setup mock loader
        mock_pipeline = PipelineDefinition(
            name="deploy",
            description="Deploy to production",
            steps=[PipelineStep(id="build", exec="npm run build")],
        )
        http_server.services.workflow_loader.load_pipeline.return_value = mock_pipeline

        # Setup mock executor to raise an error
        http_server.services.pipeline_executor.execute = AsyncMock(
            side_effect=RuntimeError("Execution failed")
        )

        response = client.post(
            "/api/pipelines/run",
            json={"name": "deploy", "inputs": {}},
        )

        assert response.status_code == 500
        assert "error" in response.json()["detail"].lower()
