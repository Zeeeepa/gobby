from datetime import datetime
from unittest.mock import MagicMock

import pytest

from gobby.storage.messages import LocalMessageManager
from gobby.sessions.transcripts.base import ParsedMessage
from gobby.storage.database import LocalDatabase


@pytest.fixture
def mock_db():
    return MagicMock(spec=LocalDatabase)


@pytest.fixture
def manager(mock_db):
    return LocalMessageManager(mock_db)


@pytest.fixture
def sample_message():
    return ParsedMessage(
        index=1,
        role="user",
        content="Hello",
        content_type="text",
        tool_name=None,
        tool_input=None,
        tool_result=None,
        timestamp=datetime.fromisoformat("2024-01-01T12:00:00"),
        raw_json={"type": "user", "message": "Hello"},
    )


@pytest.mark.asyncio
async def test_store_messages_empty(manager):
    assert await manager.store_messages("session-1", []) == 0
    manager.db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_store_messages_single(manager, mock_db, sample_message):
    count = await manager.store_messages("session-1", [sample_message])

    assert count == 1
    mock_db.execute.assert_called_once()

    # Verify arguments passed to execute
    call_args = mock_db.execute.call_args
    assert call_args is not None
    query, params = call_args[0]

    assert "INSERT INTO session_messages" in query
    assert params[0] == "session-1"
    assert params[1] == sample_message.index
    assert params[2] == sample_message.role
    assert params[3] == sample_message.content
    assert params[8] == sample_message.timestamp.isoformat()


@pytest.mark.asyncio
async def test_store_messages_with_tools(manager, mock_db):
    msg = ParsedMessage(
        index=2,
        role="assistant",
        content="",
        content_type="tool_use",
        tool_name="test_tool",
        tool_input={"arg": "val"},
        tool_result=None,
        timestamp=datetime.now(),
        raw_json={},
    )

    await manager.store_messages("session-1", [msg])

    call_args = mock_db.execute.call_args
    _, params = call_args[0]

    # Verify tool input was JSON encoded
    assert params[5] == "test_tool"
    assert params[6] == '{"arg": "val"}'


@pytest.mark.asyncio
async def test_get_messages(manager, mock_db):
    mock_db.fetchall.return_value = [
        {"session_id": "s1", "message_index": 1, "content": "msg1"},
        {"session_id": "s1", "message_index": 2, "content": "msg2"},
    ]

    messages = await manager.get_messages("s1")

    assert len(messages) == 2
    assert messages[0]["content"] == "msg1"

    # Check query structure
    call_args = mock_db.fetchall.call_args
    query, params = call_args[0]
    assert "WHERE session_id = ?" in query
    assert params[0] == "s1"


@pytest.mark.asyncio
async def test_get_messages_with_filters(manager, mock_db):
    mock_db.fetchall.return_value = []

    await manager.get_messages("s1", role="user", limit=10, offset=5)

    call_args = mock_db.fetchall.call_args
    query, params = call_args[0]

    assert "AND role = ?" in query
    assert "user" in params
    assert params[-2] == 10  # limit
    assert params[-1] == 5  # offset


@pytest.mark.asyncio
async def test_get_state(manager, mock_db):
    mock_db.fetchone.return_value = {
        "session_id": "s1",
        "last_byte_offset": 100,
        "last_message_index": 5,
    }

    state = await manager.get_state("s1")

    assert state is not None
    assert state["last_byte_offset"] == 100
    mock_db.fetchone.assert_called_with(
        "SELECT * FROM session_message_state WHERE session_id = ?", ("s1",)
    )


@pytest.mark.asyncio
async def test_get_state_none(manager, mock_db):
    mock_db.fetchone.return_value = None
    state = await manager.get_state("s1")
    assert state is None


@pytest.mark.asyncio
async def test_update_state(manager, mock_db):
    await manager.update_state("s1", byte_offset=200, message_index=10)

    call_args = mock_db.execute.call_args
    query, params = call_args[0]

    assert "INSERT INTO session_message_state" in query
    assert params[0] == "s1"
    assert params[1] == 200  # byte_offset
    assert params[2] == 10  # message_index
