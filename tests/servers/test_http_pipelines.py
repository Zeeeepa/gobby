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


class TestPipelinesGetEndpoint:
    """Tests for GET /api/pipelines/{execution_id} endpoint."""

    @pytest.fixture
    def mock_execution_manager(self):
        """Create a mock execution manager."""
        return MagicMock()

    @pytest.fixture
    def http_server_with_manager(
        self,
        session_storage: LocalSessionManager,
        mock_pipeline_executor,
        mock_workflow_loader,
        mock_execution_manager,
    ) -> HTTPServer:
        """Create an HTTP server instance with execution manager."""
        services = ServiceContainer(
            config=None,
            database=session_storage.db,
            session_manager=session_storage,
            task_manager=MagicMock(),
            pipeline_executor=mock_pipeline_executor,
            workflow_loader=mock_workflow_loader,
        )
        # Add execution manager via services attribute
        services.pipeline_execution_manager = mock_execution_manager
        return HTTPServer(
            services=services,
            port=60887,
            test_mode=True,
        )

    @pytest.fixture
    def client_with_manager(self, http_server_with_manager: HTTPServer) -> Iterator[TestClient]:
        """Create a test client with execution manager."""
        with patch("gobby.servers.http.HookManager") as MockHM:
            mock_instance = MockHM.return_value
            mock_instance._stop_registry = MagicMock()
            mock_instance.shutdown = MagicMock()
            with TestClient(http_server_with_manager.app) as client:
                yield client

    def test_get_execution_success(self, client_with_manager, http_server_with_manager) -> None:
        """Verify GET /api/pipelines/{id} returns execution details."""
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        mock_execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="deploy",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:01:00Z",
        )
        http_server_with_manager.services.pipeline_execution_manager.get_execution.return_value = (
            mock_execution
        )
        http_server_with_manager.services.pipeline_execution_manager.get_steps_for_execution.return_value = []

        response = client_with_manager.get("/api/pipelines/pe-abc123")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "pe-abc123"
        assert data["pipeline_name"] == "deploy"
        assert data["status"] == "completed"

    def test_get_execution_includes_steps(
        self, client_with_manager, http_server_with_manager
    ) -> None:
        """Verify GET /api/pipelines/{id} includes step_executions array."""
        from gobby.workflows.pipeline_state import (
            ExecutionStatus,
            PipelineExecution,
            StepExecution,
            StepStatus,
        )

        mock_execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="deploy",
            project_id="proj-1",
            status=ExecutionStatus.RUNNING,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:01:00Z",
        )
        mock_steps = [
            StepExecution(
                id=1,
                execution_id="pe-abc123",
                step_id="build",
                status=StepStatus.COMPLETED,
            ),
            StepExecution(
                id=2,
                execution_id="pe-abc123",
                step_id="test",
                status=StepStatus.RUNNING,
            ),
        ]
        http_server_with_manager.services.pipeline_execution_manager.get_execution.return_value = (
            mock_execution
        )
        http_server_with_manager.services.pipeline_execution_manager.get_steps_for_execution.return_value = mock_steps

        response = client_with_manager.get("/api/pipelines/pe-abc123")

        assert response.status_code == 200
        data = response.json()
        assert "steps" in data
        assert len(data["steps"]) == 2
        assert data["steps"][0]["step_id"] == "build"
        assert data["steps"][0]["status"] == "completed"
        assert data["steps"][1]["step_id"] == "test"
        assert data["steps"][1]["status"] == "running"

    def test_get_execution_not_found(self, client_with_manager, http_server_with_manager) -> None:
        """Verify GET /api/pipelines/{id} returns 404 for unknown id."""
        http_server_with_manager.services.pipeline_execution_manager.get_execution.return_value = (
            None
        )

        response = client_with_manager.get("/api/pipelines/pe-nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestPipelinesApproveEndpoint:
    """Tests for POST /api/pipelines/approve/{token} endpoint."""

    def test_approve_success(self, client, http_server) -> None:
        """Verify POST /api/pipelines/approve/{token} calls executor.approve()."""
        from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution

        mock_execution = PipelineExecution(
            id="pe-abc123",
            pipeline_name="deploy",
            project_id="proj-1",
            status=ExecutionStatus.COMPLETED,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:01:00Z",
        )
        http_server.services.pipeline_executor.approve = AsyncMock(return_value=mock_execution)

        response = client.post("/api/pipelines/approve/approval-token-xyz")

        assert response.status_code == 200
        http_server.services.pipeline_executor.approve.assert_called_once_with(
            "approval-token-xyz", approved_by=None
        )
        data = response.json()
        assert data["status"] == "completed"
        assert data["execution_id"] == "pe-abc123"

    def test_approve_invalid_token(self, client, http_server) -> None:
        """Verify POST /api/pipelines/approve/{token} returns 404 for invalid token."""
        http_server.services.pipeline_executor.approve = AsyncMock(
            side_effect=ValueError("Invalid token")
        )

        response = client.post("/api/pipelines/approve/invalid-token")

        assert response.status_code == 404
        assert "invalid" in response.json()["detail"].lower()

    def test_approve_returns_next_approval(self, client, http_server) -> None:
        """Verify POST /api/pipelines/approve returns 202 if more approvals needed."""
        from gobby.workflows.pipeline_state import ApprovalRequired

        http_server.services.pipeline_executor.approve = AsyncMock(
            side_effect=ApprovalRequired(
                execution_id="pe-abc123",
                step_id="deploy-step",
                token="next-approval-token",
                message="Another approval required",
            )
        )

        response = client.post("/api/pipelines/approve/approval-token-xyz")

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "waiting_approval"
        assert data["token"] == "next-approval-token"
