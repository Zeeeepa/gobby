"""Tests for the SessionManager service layer."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gobby.sessions.manager import SessionManager
from gobby.storage.database import LocalDatabase
from gobby.storage.projects import LocalProjectManager
from gobby.storage.sessions import LocalSessionManager


@pytest.fixture
def session_storage(temp_db: LocalDatabase) -> LocalSessionManager:
    """Create session storage with temp database."""
    return LocalSessionManager(temp_db)


@pytest.fixture
def project_storage(temp_db: LocalDatabase) -> LocalProjectManager:
    """Create project storage with temp database."""
    return LocalProjectManager(temp_db)


@pytest.fixture
def test_project(project_storage: LocalProjectManager) -> dict:
    """Create a test project."""
    project = project_storage.create(name="test-project", repo_path="/tmp/test")
    return project.to_dict()


@pytest.fixture
def session_mgr(session_storage: LocalSessionManager) -> SessionManager:
    """Create a SessionManager instance for testing."""
    return SessionManager(
        session_storage=session_storage,
        logger_instance=MagicMock(),
    )


class TestSessionManagerRegistration:
    """Tests for session registration."""

    def test_register_session(
        self,
        session_mgr: SessionManager,
        test_project: dict,
    ):
        """Test registering a new session."""
        session_id = session_mgr.register_session(
            external_id="test-cli-123",
            machine_id="machine-abc",
            source="claude",
            project_id=test_project["id"],
        )

        assert session_id is not None
        assert len(session_id) == 36  # UUID format

    def test_register_session_with_all_fields(
        self,
        session_mgr: SessionManager,
        test_project: dict,
    ):
        """Test registering session with all optional fields."""
        session_id = session_mgr.register_session(
            external_id="full-cli-123",
            machine_id="machine-xyz",
            source="gemini",
            project_id=test_project["id"],
            parent_session_id=None,  # Use None instead of invalid UUID
            jsonl_path="/path/to/transcript.jsonl",
            title="Test Session Title",
            git_branch="feature/test",
        )

        assert session_id is not None
        # Verify session data
        session = session_mgr.get_session(session_id)
        assert session is not None
        assert session["title"] == "Test Session Title"
        assert session["git_branch"] == "feature/test"

    def test_register_caches_mapping(
        self,
        session_mgr: SessionManager,
        test_project: dict,
    ):
        """Test that registration caches external_id -> session_id mapping."""
        session_id = session_mgr.register_session(
            external_id="cached-cli",
            machine_id="machine",
            source="claude",
            project_id=test_project["id"],
        )

        # Should be cached (keyed by (external_id, source))
        cached_id = session_mgr.get_session_id("cached-cli", "claude")
        assert cached_id == session_id

    def test_register_extracts_git_branch(
        self,
        session_mgr: SessionManager,
        test_project: dict,
    ):
        """Test git branch is set when provided."""
        session_id = session_mgr.register_session(
            external_id="git-test",
            machine_id="machine",
            source="claude",
            project_id=test_project["id"],
            git_branch="main",
        )

        session = session_mgr.get_session(session_id)
        assert session is not None
        assert session["git_branch"] == "main"


class TestSessionManagerLookup:
    """Tests for session lookup."""

    def test_get_session_id_cached(
        self,
        session_mgr: SessionManager,
        test_project: dict,
    ):
        """Test getting cached session_id."""
        session_id = session_mgr.register_session(
            external_id="lookup-test",
            machine_id="machine",
            source="claude",
            project_id=test_project["id"],
        )

        result = session_mgr.get_session_id("lookup-test", "claude")
        assert result == session_id

    def test_get_session_id_not_cached(self, session_mgr: SessionManager):
        """Test getting session_id when not cached returns None."""
        result = session_mgr.get_session_id("nonexistent", "claude")
        assert result is None

    def test_lookup_session_id(
        self,
        session_mgr: SessionManager,
        test_project: dict,
    ):
        """Test looking up session_id from database."""
        session_id = session_mgr.register_session(
            external_id="db-lookup",
            machine_id="machine-1",
            source="codex",
            project_id=test_project["id"],
        )

        # Clear cache
        session_mgr._session_mapping.clear()

        # Should look up from database (requires full composite key)
        result = session_mgr.lookup_session_id(
            external_id="db-lookup",
            source="codex",
            machine_id="machine-1",
            project_id=test_project["id"],
        )
        assert result == session_id

    def test_lookup_session_id_caches_result(
        self,
        session_mgr: SessionManager,
        test_project: dict,
    ):
        """Test that lookup caches the result."""
        session_id = session_mgr.register_session(
            external_id="cache-lookup",
            machine_id="machine",
            source="claude",
            project_id=test_project["id"],
        )

        # Clear cache
        session_mgr._session_mapping.clear()

        # Lookup with full composite key
        session_mgr.lookup_session_id(
            external_id="cache-lookup",
            source="claude",
            machine_id="machine",
            project_id=test_project["id"],
        )

        # Should now be cached (keyed by (external_id, source))
        assert session_mgr.get_session_id("cache-lookup", "claude") == session_id

    def test_get_session(
        self,
        session_mgr: SessionManager,
        test_project: dict,
    ):
        """Test getting full session data."""
        session_id = session_mgr.register_session(
            external_id="full-data",
            machine_id="machine",
            source="gemini",
            project_id=test_project["id"],
            title="Full Data Session",
        )

        session = session_mgr.get_session(session_id)
        assert session is not None
        assert session["id"] == session_id
        assert session["external_id"] == "full-data"
        assert session["source"] == "gemini"
        assert session["title"] == "Full Data Session"

    def test_get_session_nonexistent(self, session_mgr: SessionManager):
        """Test getting nonexistent session returns None."""
        result = session_mgr.get_session("nonexistent-uuid")
        assert result is None


class TestSessionManagerStatus:
    """Tests for session status management."""

    def test_update_session_status(
        self,
        session_mgr: SessionManager,
        test_project: dict,
    ):
        """Test updating session status."""
        session_id = session_mgr.register_session(
            external_id="status-test",
            machine_id="machine",
            source="claude",
            project_id=test_project["id"],
        )

        result = session_mgr.update_session_status(session_id, "paused")
        assert result is True

        session = session_mgr.get_session(session_id)
        assert session is not None
        assert session["status"] == "paused"

    def test_mark_session_expired(
        self,
        session_mgr: SessionManager,
        test_project: dict,
    ):
        """Test marking session as expired."""
        session_id = session_mgr.register_session(
            external_id="expire-test",
            machine_id="machine",
            source="claude",
            project_id=test_project["id"],
        )

        result = session_mgr.mark_session_expired(session_id)
        assert result is True

        session = session_mgr.get_session(session_id)
        assert session is not None
        assert session["status"] == "expired"

    def test_update_nonexistent_session(self, session_mgr: SessionManager):
        """Test updating status of nonexistent session."""
        result = session_mgr.update_session_status("nonexistent", "active")
        assert result is False


class TestSessionManagerHandoff:
    """Tests for session handoff functionality."""

    def test_find_parent_session(
        self,
        session_mgr: SessionManager,
        test_project: dict,
    ):
        """Test finding parent session for handoff."""
        # Create and mark a session as handoff_ready
        parent_id = session_mgr.register_session(
            external_id="parent-cli",
            machine_id="handoff-machine",
            source="claude",
            project_id=test_project["id"],
        )
        session_mgr.update_session_status(parent_id, "handoff_ready")

        # Update summary for handoff
        session_mgr._storage.update_summary(parent_id, summary_markdown="Test summary content")

        # Find parent (with very short max_attempts for test speed)
        result = session_mgr.find_parent_session(
            machine_id="handoff-machine",
            source="claude",
            project_id=test_project["id"],
            max_attempts=1,
        )

        assert result is not None
        found_id, summary = result
        assert found_id == parent_id
        assert summary == "Test summary content"

    def test_find_parent_session_no_handoff_ready(
        self,
        session_mgr: SessionManager,
        test_project: dict,
    ):
        """Test finding parent when none marked handoff_ready."""
        # Create an active session
        session_mgr.register_session(
            external_id="active-session",
            machine_id="test-machine",
            source="claude",
            project_id=test_project["id"],
        )

        # Should not find any parent (max_attempts=1 for speed)
        result = session_mgr.find_parent_session(
            machine_id="test-machine",
            source="claude",
            project_id=test_project["id"],
            max_attempts=1,
        )

        assert result is None


class TestSessionManagerSummaryFile:
    """Tests for summary file reading."""

    def test_read_summary_file(
        self,
        session_mgr: SessionManager,
        temp_dir: Path,
    ):
        """Test reading summary from file."""
        # Create summary directory and file
        summary_dir = temp_dir / "session_summaries"
        summary_dir.mkdir()

        session_id = "test-session-uuid"
        summary_file = summary_dir / f"session_2024-01-01_{session_id}.md"
        summary_file.write_text("# Summary\nTest content")

        # Configure session manager with test path
        from gobby.config.app import DaemonConfig, SessionSummaryConfig

        config = DaemonConfig(
            session_summary=SessionSummaryConfig(summary_file_path=str(summary_dir))
        )
        session_mgr._config = config

        result = session_mgr.read_summary_file(session_id)
        assert result == "# Summary\nTest content"

    def test_read_summary_file_not_found(
        self,
        session_mgr: SessionManager,
        temp_dir: Path,
    ):
        """Test reading nonexistent summary file returns None."""
        result = session_mgr.read_summary_file("nonexistent-uuid")
        assert result is None


class TestSessionManagerCaching:
    """Tests for session caching functionality."""

    def test_cache_session_mapping(self, session_mgr: SessionManager):
        """Test manually caching session mapping."""
        session_mgr.cache_session_mapping("manual-cli", "claude", "manual-session-id")

        result = session_mgr.get_session_id("manual-cli", "claude")
        assert result == "manual-session-id"

    def test_thread_safety(
        self,
        session_mgr: SessionManager,
        test_project: dict,
    ):
        """Test that session operations are thread-safe."""
        import threading

        results = []
        errors = []

        def register_session(index: int):
            try:
                session_id = session_mgr.register_session(
                    external_id=f"thread-{index}",
                    machine_id=f"machine-{index}",
                    source="claude",
                    project_id=test_project["id"],
                )
                results.append((index, session_id))
            except Exception as e:
                errors.append((index, e))

        threads = [threading.Thread(target=register_session, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All registrations should succeed
        assert len(errors) == 0
        assert len(results) == 5

        # All session IDs should be unique
        session_ids = [sid for _, sid in results]
        assert len(set(session_ids)) == 5


# ==============================================================================
# Tests for Handoff Artifact Context Injection (TDD Red Phase)
# These tests define expected behavior for artifact injection in handoff context.
# Tests will skip/fail until implementation is complete.
# ==============================================================================


def has_generate_handoff_context() -> bool:
    """Check if generate_handoff_context method exists."""
    return hasattr(SessionManager, "generate_handoff_context")


class TestHandoffArtifactContext:
    """Tests for artifact context injection in session handoffs."""

    @pytest.mark.skipif(
        not has_generate_handoff_context(),
        reason="generate_handoff_context not yet implemented",
    )
    def test_generate_handoff_context_includes_artifacts(
        self,
        session_mgr: SessionManager,
        session_storage,
        test_project: dict,
        temp_db: LocalDatabase,
    ):
        """Verify generate_handoff_context includes relevant artifacts."""
        from gobby.storage.artifacts import LocalArtifactManager

        # Create session with artifacts
        session_id = session_mgr.register_session(
            external_id="artifact-session",
            machine_id="test-machine",
            source="claude",
            project_id=test_project["id"],
        )

        # Create artifacts for the session
        artifact_manager = LocalArtifactManager(temp_db)
        artifact_manager.create_artifact(
            session_id=session_id,
            artifact_type="code",
            content="function calculateTotal(items) { return items.reduce((s, i) => s + i.price, 0); }",
            source_file="utils.js",
            metadata={"language": "javascript"},
        )

        # Generate handoff context
        context = session_mgr.generate_handoff_context(session_id)

        assert "artifacts" in context or "code" in context.lower()
        assert "calculateTotal" in context

    @pytest.mark.skipif(
        not has_generate_handoff_context(),
        reason="generate_handoff_context not yet implemented",
    )
    def test_generate_handoff_context_uses_session_lineage(
        self,
        session_mgr: SessionManager,
        session_storage,
        test_project: dict,
        temp_db: LocalDatabase,
    ):
        """Verify artifact search uses session lineage (parent sessions)."""
        from gobby.storage.artifacts import LocalArtifactManager

        # Create parent session with artifacts
        parent_id = session_mgr.register_session(
            external_id="parent-artifact-session",
            machine_id="test-machine",
            source="claude",
            project_id=test_project["id"],
        )

        artifact_manager = LocalArtifactManager(temp_db)
        artifact_manager.create_artifact(
            session_id=parent_id,
            artifact_type="code",
            content="// Parent session code artifact",
            source_file="parent.js",
        )

        # Create child session linked to parent
        child_id = session_mgr.register_session(
            external_id="child-artifact-session",
            machine_id="test-machine",
            source="claude",
            project_id=test_project["id"],
            parent_session_id=parent_id,
        )

        artifact_manager.create_artifact(
            session_id=child_id,
            artifact_type="code",
            content="// Child session code artifact",
            source_file="child.js",
        )

        # Generate handoff context for child - should include parent artifacts too
        context = session_mgr.generate_handoff_context(child_id, include_parent_artifacts=True)

        assert "Parent session code artifact" in context
        assert "Child session code artifact" in context

    @pytest.mark.skipif(
        not has_generate_handoff_context(),
        reason="generate_handoff_context not yet implemented",
    )
    def test_code_artifacts_formatted_with_syntax_markers(
        self,
        session_mgr: SessionManager,
        session_storage,
        test_project: dict,
        temp_db: LocalDatabase,
    ):
        """Verify code artifacts have language syntax markers in context."""
        from gobby.storage.artifacts import LocalArtifactManager

        session_id = session_mgr.register_session(
            external_id="syntax-test-session",
            machine_id="test-machine",
            source="claude",
            project_id=test_project["id"],
        )

        artifact_manager = LocalArtifactManager(temp_db)
        artifact_manager.create_artifact(
            session_id=session_id,
            artifact_type="code",
            content="def hello():\n    print('Hello World')",
            source_file="hello.py",
            metadata={"language": "python"},
        )

        context = session_mgr.generate_handoff_context(session_id)

        # Should include markdown code fence with language
        assert "```python" in context or "```py" in context
        assert "def hello():" in context

    @pytest.mark.skipif(
        not has_generate_handoff_context(),
        reason="generate_handoff_context not yet implemented",
    )
    def test_artifact_metadata_included_in_context(
        self,
        session_mgr: SessionManager,
        session_storage,
        test_project: dict,
        temp_db: LocalDatabase,
    ):
        """Verify artifact metadata is included in context."""
        from gobby.storage.artifacts import LocalArtifactManager

        session_id = session_mgr.register_session(
            external_id="metadata-test-session",
            machine_id="test-machine",
            source="claude",
            project_id=test_project["id"],
        )

        artifact_manager = LocalArtifactManager(temp_db)
        artifact_manager.create_artifact(
            session_id=session_id,
            artifact_type="code",
            content="const API_ENDPOINT = '/api/v1/users';",
            source_file="config/api.ts",
            line_start=42,
            line_end=42,
            metadata={"language": "typescript"},
        )

        context = session_mgr.generate_handoff_context(session_id)

        # Should include source file reference
        assert "api.ts" in context or "config" in context
        # Should reference line numbers if available
        assert "42" in context or "line" in context.lower()

    @pytest.mark.skipif(
        not has_generate_handoff_context(),
        reason="generate_handoff_context not yet implemented",
    )
    def test_configurable_artifact_inclusion_limit(
        self,
        session_mgr: SessionManager,
        session_storage,
        test_project: dict,
        temp_db: LocalDatabase,
    ):
        """Verify artifact inclusion respects configurable limit."""
        from gobby.storage.artifacts import LocalArtifactManager

        session_id = session_mgr.register_session(
            external_id="limit-test-session",
            machine_id="test-machine",
            source="claude",
            project_id=test_project["id"],
        )

        artifact_manager = LocalArtifactManager(temp_db)

        # Create 10 artifacts
        for i in range(10):
            artifact_manager.create_artifact(
                session_id=session_id,
                artifact_type="code",
                content=f"// Artifact number {i}",
                source_file=f"file{i}.js",
            )

        # Generate with limit of 3
        context = session_mgr.generate_handoff_context(session_id, max_artifacts=3)

        # Count how many artifacts appear
        artifact_count = sum(1 for i in range(10) if f"Artifact number {i}" in context)
        assert artifact_count <= 3

    @pytest.mark.skipif(
        not has_generate_handoff_context(),
        reason="generate_handoff_context not yet implemented",
    )
    def test_context_size_limits_respected(
        self,
        session_mgr: SessionManager,
        session_storage,
        test_project: dict,
        temp_db: LocalDatabase,
    ):
        """Verify context respects size limits."""
        from gobby.storage.artifacts import LocalArtifactManager

        session_id = session_mgr.register_session(
            external_id="size-limit-session",
            machine_id="test-machine",
            source="claude",
            project_id=test_project["id"],
        )

        artifact_manager = LocalArtifactManager(temp_db)

        # Create a large artifact (10KB)
        large_content = "x" * 10000
        artifact_manager.create_artifact(
            session_id=session_id,
            artifact_type="code",
            content=large_content,
            source_file="large.js",
        )

        # Generate with small size limit
        context = session_mgr.generate_handoff_context(session_id, max_context_size=1000)

        # Context should be truncated or artifact excluded
        assert len(context) <= 1500  # Allow some overhead for formatting

    @pytest.mark.skipif(
        not has_generate_handoff_context(),
        reason="generate_handoff_context not yet implemented",
    )
    def test_error_artifacts_included_in_context(
        self,
        session_mgr: SessionManager,
        session_storage,
        test_project: dict,
        temp_db: LocalDatabase,
    ):
        """Verify error artifacts are included in handoff context."""
        from gobby.storage.artifacts import LocalArtifactManager

        session_id = session_mgr.register_session(
            external_id="error-artifact-session",
            machine_id="test-machine",
            source="claude",
            project_id=test_project["id"],
        )

        artifact_manager = LocalArtifactManager(temp_db)
        artifact_manager.create_artifact(
            session_id=session_id,
            artifact_type="error",
            content="TypeError: Cannot read property 'foo' of undefined\n  at bar.js:42",
        )

        context = session_mgr.generate_handoff_context(session_id)

        assert "TypeError" in context
        assert "Cannot read property" in context

    @pytest.mark.skipif(
        not has_generate_handoff_context(),
        reason="generate_handoff_context not yet implemented",
    )
    def test_diff_artifacts_included_in_context(
        self,
        session_mgr: SessionManager,
        session_storage,
        test_project: dict,
        temp_db: LocalDatabase,
    ):
        """Verify diff artifacts are included in handoff context."""
        from gobby.storage.artifacts import LocalArtifactManager

        session_id = session_mgr.register_session(
            external_id="diff-artifact-session",
            machine_id="test-machine",
            source="claude",
            project_id=test_project["id"],
        )

        artifact_manager = LocalArtifactManager(temp_db)
        artifact_manager.create_artifact(
            session_id=session_id,
            artifact_type="diff",
            content="--- a/file.js\n+++ b/file.js\n@@ -1,3 +1,4 @@\n const x = 1;\n+const y = 2;",
            source_file="file.js",
        )

        context = session_mgr.generate_handoff_context(session_id)

        assert "diff" in context.lower() or "---" in context
        assert "+const y = 2;" in context or "const y = 2" in context

    @pytest.mark.skipif(
        not has_generate_handoff_context(),
        reason="generate_handoff_context not yet implemented",
    )
    def test_no_artifacts_returns_basic_context(
        self,
        session_mgr: SessionManager,
        session_storage,
        test_project: dict,
    ):
        """Verify handoff context works when no artifacts exist."""
        session_id = session_mgr.register_session(
            external_id="no-artifacts-session",
            machine_id="test-machine",
            source="claude",
            project_id=test_project["id"],
        )

        # Generate context with no artifacts
        context = session_mgr.generate_handoff_context(session_id)

        # Should return some context (possibly summary-only or empty artifacts section)
        assert context is not None
        assert isinstance(context, str)
