"""Pytest configuration and shared fixtures for Gobby tests."""

import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from gobby.config.app import DaemonConfig
    from gobby.storage.database import LocalDatabase
    from gobby.storage.mcp import LocalMCPManager
    from gobby.storage.projects import LocalProjectManager
    from gobby.storage.sessions import LocalSessionManager


@pytest.fixture
def temp_dir() -> Iterator[Path]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_db(temp_dir: Path) -> Iterator["LocalDatabase"]:
    """Create a temporary database for testing."""
    from gobby.storage.database import LocalDatabase
    from gobby.storage.migrations import run_migrations

    db_path = temp_dir / "test.db"
    db = LocalDatabase(db_path)
    run_migrations(db)
    yield db
    db.close()


@pytest.fixture
def session_manager(temp_db: "LocalDatabase") -> "LocalSessionManager":
    """Create a session manager with temp database."""
    from gobby.storage.sessions import LocalSessionManager

    return LocalSessionManager(temp_db)


@pytest.fixture
def project_manager(temp_db: "LocalDatabase") -> "LocalProjectManager":
    """Create a project manager with temp database."""
    from gobby.storage.projects import LocalProjectManager

    return LocalProjectManager(temp_db)


@pytest.fixture
def mcp_manager(temp_db: "LocalDatabase") -> "LocalMCPManager":
    """Create an MCP manager with temp database."""
    from gobby.storage.mcp import LocalMCPManager

    return LocalMCPManager(temp_db)


@pytest.fixture
def sample_project(project_manager: "LocalProjectManager") -> dict:
    """Create a sample project for testing."""
    project = project_manager.create(
        name="test-project",
        repo_path="/tmp/test-project",
        github_url="https://github.com/test/test-project",
    )
    return project.to_dict()


@pytest.fixture
def default_config() -> "DaemonConfig":
    """Create a default DaemonConfig for testing."""
    from gobby.config.app import DaemonConfig

    return DaemonConfig()


@pytest.fixture
def mock_machine_id() -> Iterator[str]:
    """Mock the machine ID for consistent testing."""
    machine_id = "test-machine-id-12345"
    with patch("gobby.utils.machine_id.get_machine_id", return_value=machine_id):
        yield machine_id


@pytest.fixture
def mock_llm_service() -> MagicMock:
    """Create a mock LLM service for testing."""
    service = MagicMock()
    service.generate.return_value = "Mock LLM response"
    return service


@pytest.fixture(autouse=True)
def protect_production_resources(request: pytest.FixtureRequest, temp_dir: Path) -> Iterator[None]:
    """
    Defensive fixture to prevent tests from touching production resources.

    Forces all tests to use temporary paths for database and logging,
    unless explicitly opting out with @pytest.mark.no_config_protection.
    """
    if request.node.get_closest_marker("no_config_protection"):
        yield
        return

    import os

    from gobby.config.app import DaemonConfig

    # Create safe paths
    safe_db_path = temp_dir / "test-safe.db"
    safe_logs_dir = temp_dir / "logs"
    safe_logs_dir.mkdir()

    safe_log_client = safe_logs_dir / "gobby.log"
    safe_log_error = safe_logs_dir / "gobby-error.log"
    safe_log_mcp_server = safe_logs_dir / "mcp-server.log"
    safe_log_mcp_client = safe_logs_dir / "mcp-client.log"

    # Set environment variables as a first line of defense
    env_vars = {
        "GOBBY_TEST_PROTECT": "1",  # Enable safety switch in app.py and database.py
        "GOBBY_DATABASE_PATH": str(safe_db_path),
        "GOBBY_LOGGING_CLIENT": str(safe_log_client),
        "GOBBY_LOGGING_CLIENT_ERROR": str(safe_log_error),
        "GOBBY_LOGGING_MCP_SERVER": str(safe_log_mcp_server),
        "GOBBY_LOGGING_MCP_CLIENT": str(safe_log_mcp_client),
    }

    with patch.dict(os.environ, env_vars):
        # Patch load_config to return a safe config
        # We need to use a side_effect to allow partial loading if needed,
        # but for most tests returning a safe config object is best.
        # However, many tests mock load_config themselves.
        # We'll use a wrapper that returns our safe config unless arguments suggest otherwise.

        real_load_config = None
        try:
            from gobby.config import app

            real_load_config = app.load_config
        except ImportError:
            pass

        def safe_load_config(*args, **kwargs):
            # If creating default, let it happen but in safe location if possible
            # But simpler is to just return a safe config object
            config = DaemonConfig(
                database_path=str(safe_db_path),
                logging={
                    "client": str(safe_log_client),
                    "client_error": str(safe_log_error),
                    "mcp_server": str(safe_log_mcp_server),
                    "mcp_client": str(safe_log_mcp_client),
                },
            )
            # Apply overrides if present (logic from real load_config)
            if "cli_overrides" in kwargs and kwargs["cli_overrides"]:
                from gobby.config.app import apply_cli_overrides

                start_dict = config.model_dump(exclude_none=True)
                final_dict = apply_cli_overrides(start_dict, kwargs["cli_overrides"])
                config = DaemonConfig(**final_dict)
            return config

        # We patch where it is defined
        with patch("gobby.config.app.load_config", side_effect=safe_load_config):
            yield
