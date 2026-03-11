"""Tests for LocalSessionMessageManager."""

from datetime import UTC, datetime

import pytest

from gobby.sessions.transcripts.base import ParsedMessage
from gobby.storage.database import LocalDatabase
from gobby.storage.session_messages import LocalSessionMessageManager
from gobby.storage.sessions import LocalSessionManager

pytestmark = pytest.mark.unit


@pytest.fixture
def message_manager(temp_db: LocalDatabase) -> LocalSessionMessageManager:
    """Create a message manager with temp database."""
    return LocalSessionMessageManager(temp_db)


@pytest.fixture
def session_id(temp_db: LocalDatabase, session_manager: LocalSessionManager) -> str:
    """Create a project and session, return the session ID."""
    from gobby.storage.projects import LocalProjectManager

    project_manager = LocalProjectManager(temp_db)
    project = project_manager.get_or_create("/tmp/test-project")

    session = session_manager.register(
        external_id="test-ext-id",
        machine_id="test-machine",
        source="test",
        project_id=project.id,
    )
    return session.id


def _make_message(index: int, role: str = "user", content: str = "hello") -> ParsedMessage:
    return ParsedMessage(
        index=index,
        role=role,
        content=content,
        content_type="text",
        tool_name=None,
        tool_input=None,
        tool_result=None,
        timestamp=datetime.now(UTC),
        raw_json={},
    )


class TestDeleteState:
    """Tests for delete_state()."""

    @pytest.mark.asyncio
    async def test_delete_state_removes_state(
        self, message_manager: LocalSessionMessageManager, session_id: str
    ) -> None:
        """delete_state removes processing state for a session."""
        # Create state first
        await message_manager.update_state(session_id, byte_offset=100, message_index=5)
        state = await message_manager.get_state(session_id)
        assert state is not None

        # Delete it
        await message_manager.delete_state(session_id)
        state = await message_manager.get_state(session_id)
        assert state is None

    @pytest.mark.asyncio
    async def test_delete_state_noop_for_nonexistent(
        self, message_manager: LocalSessionMessageManager
    ) -> None:
        """delete_state is a no-op for sessions without state."""
        # Should not raise
        await message_manager.delete_state("nonexistent-session-id")


class TestGetMaxMessageIndex:
    """Tests for get_max_message_index()."""

    @pytest.mark.asyncio
    async def test_returns_negative_one_for_no_messages(
        self, message_manager: LocalSessionMessageManager, session_id: str
    ) -> None:
        """Returns -1 when session has no messages."""
        result = await message_manager.get_max_message_index(session_id)
        assert result == -1

    @pytest.mark.asyncio
    async def test_returns_correct_max_after_storing(
        self, message_manager: LocalSessionMessageManager, session_id: str
    ) -> None:
        """Returns the highest message_index after storing messages."""
        messages = [_make_message(0), _make_message(1), _make_message(2)]
        await message_manager.store_messages(session_id, messages)

        result = await message_manager.get_max_message_index(session_id)
        assert result == 2

    @pytest.mark.asyncio
    async def test_returns_max_with_gaps(
        self, message_manager: LocalSessionMessageManager, session_id: str
    ) -> None:
        """Returns correct max even if indices have gaps."""
        messages = [_make_message(0), _make_message(5), _make_message(3)]
        await message_manager.store_messages(session_id, messages)

        result = await message_manager.get_max_message_index(session_id)
        assert result == 5

    @pytest.mark.asyncio
    async def test_returns_negative_one_for_nonexistent_session(
        self, message_manager: LocalSessionMessageManager
    ) -> None:
        """Returns -1 for a session ID with no messages."""
        result = await message_manager.get_max_message_index("nonexistent-session-id")
        assert result == -1
