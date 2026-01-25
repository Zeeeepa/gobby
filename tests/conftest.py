"""Pytest configuration and shared fixtures for Gobby tests."""

import tempfile
import tracemalloc
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from filelock import FileLock

tracemalloc.start()

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
def enable_log_propagation() -> Iterator[None]:
    """Enable log propagation for caplog tests.

    The gobby package logger has propagate=False to avoid duplicate logs in production.
    This fixture temporarily enables propagation so caplog can capture logs.
    """
    import logging

    gobby_logger = logging.getLogger("gobby")
    original_propagate = gobby_logger.propagate
    gobby_logger.propagate = True
    yield
    gobby_logger.propagate = original_propagate


@pytest.fixture(scope="session")
def safe_db_dir() -> Iterator[Path]:
    """Session-scoped temp directory for safe database.

    This directory persists for the entire test session to avoid the race condition
    where the database file is deleted before all tests finish using it.
    """
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
def protect_production_resources(
    request: pytest.FixtureRequest, temp_dir: Path, safe_db_dir: Path
) -> Iterator[None]:
    """
    Defensive fixture to prevent tests from touching production resources.

    Forces all tests to use temporary paths for database and logging,
    unless explicitly opting out with @pytest.mark.no_config_protection.

    Uses a session-scoped directory for the database to avoid race conditions
    where the database file gets deleted before all tests finish using it.
    """
    if request.node.get_closest_marker("no_config_protection"):
        yield
        return

    import os

    from gobby.config.app import DaemonConfig

    # Use session-scoped directory for database (persists for entire test session)
    # Use function-scoped temp_dir for logs (per-test isolation)
    safe_db_path = safe_db_dir / "test-safe.db"
    safe_logs_dir = temp_dir / "logs"
    safe_logs_dir.mkdir(exist_ok=True)

    # Run migrations on safe database - this is CRITICAL!
    # Code that calls LocalDatabase() without arguments will use this path via GOBBY_DATABASE_PATH.
    # Without migrations, queries will fail with "file is not a database" errors.
    # Only run migrations if the database doesn't exist yet (session-scoped, reused across tests).
    from gobby.storage.database import LocalDatabase
    from gobby.storage.migrations import run_migrations

    # Use file lock to prevent TOCTOU race condition during parallel test execution.
    # Without this, multiple pytest workers can simultaneously check exists() -> False,
    # then race to create the database, causing "file is not a database" errors.
    lock_path = safe_db_dir / "test-safe.db.lock"
    with FileLock(lock_path, timeout=60):
        if not safe_db_path.exists():
            safe_db = LocalDatabase(safe_db_path)
            run_migrations(safe_db)
            safe_db.close()

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

        try:
            from gobby.config import app

            # Capture the REAL function object before we patch anything
            # We need this identity to find other references to it
            _real_load_config = app.load_config
        except ImportError:
            _real_load_config = None

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

        # PATCHING STRATEGY:
        # standard patch() only patches the name in the target module.
        # But if other modules (like gobby.runner) have already done "from gobby.config.app import load_config",
        # they have a reference to the OLD function object.
        # We must find ALL references to the old function and patch them too.

        # 1. Standard patch for the definition (covers future imports)
        p = patch("gobby.config.app.load_config", side_effect=safe_load_config)
        p.start()

        # 2. Scan sys.modules for rogue references
        patched_modules = []
        if _real_load_config:
            import sys

            for mod_name, mod in list(sys.modules.items()):
                # Skip our own test modules or things that might be weird
                if not mod or not hasattr(mod, "__dict__"):
                    continue

                # Iterate over module attributes
                updates = {}
                try:
                    for attr_name, attr_val in mod.__dict__.items():
                        if attr_val is _real_load_config:
                            updates[attr_name] = safe_load_config
                except Exception:
                    # Some modules might error on iteration or access
                    continue

                # Apply updates
                if updates:
                    for attr_name, new_val in updates.items():
                        setattr(mod, attr_name, new_val)
                    patched_modules.append((mod, updates))

        yield

        # Restore everything
        p.stop()
        for mod, updates in patched_modules:
            for attr_name in updates:
                if _real_load_config is not None:
                    setattr(mod, attr_name, _real_load_config)
                else:
                    # Remove the patched attribute instead of setting to None
                    try:
                        delattr(mod, attr_name)
                    except AttributeError:
                        pass  # Attribute already removed
