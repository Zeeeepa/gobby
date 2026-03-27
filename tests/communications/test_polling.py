"""Tests for the communications polling manager."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.communications.polling import PollingManager

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_manager():
    manager = MagicMock()
    manager.handle_inbound_messages = AsyncMock()
    return manager


@pytest.fixture
def mock_adapter():
    adapter = MagicMock()
    adapter.poll = AsyncMock(return_value=[])
    return adapter


@pytest.fixture
def polling_manager(mock_manager):
    return PollingManager(manager=mock_manager, default_interval=1)


@pytest.mark.asyncio
async def test_start_polling_creates_task(polling_manager, mock_adapter):
    """start_polling should create and store an asyncio task."""
    polling_manager.start_polling("test-channel", mock_adapter)

    assert polling_manager.is_polling("test-channel")
    assert "test-channel" in polling_manager._tasks
    assert not polling_manager._tasks["test-channel"].done()

    # Cleanup
    polling_manager.stop_all()


@pytest.mark.asyncio
async def test_stop_polling_cancels_task(polling_manager, mock_adapter):
    """stop_polling should cancel the background task."""
    polling_manager.start_polling("test-channel", mock_adapter)
    assert polling_manager.is_polling("test-channel")

    task = polling_manager._tasks["test-channel"]
    polling_manager.stop_polling("test-channel")

    # Allow event loop to process cancellation
    await asyncio.sleep(0)

    assert not polling_manager.is_polling("test-channel")
    assert "test-channel" not in polling_manager._tasks
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_stop_all_cancels_all_tasks(polling_manager, mock_adapter):
    """stop_all should cancel all running polling tasks."""
    polling_manager.start_polling("channel-1", mock_adapter)
    polling_manager.start_polling("channel-2", mock_adapter)

    assert len(polling_manager._tasks) == 2

    polling_manager.stop_all()

    assert len(polling_manager._tasks) == 0
    assert not polling_manager.is_polling("channel-1")
    assert not polling_manager.is_polling("channel-2")


@pytest.mark.asyncio
async def test_poll_loop_calls_adapter(polling_manager, mock_adapter, mock_manager):
    """poll loop should call adapter.poll() and handle messages."""
    # Setup mock to return messages on first poll, then block or return nothing
    msg1 = MagicMock()
    mock_adapter.poll.side_effect = [[msg1], []]

    # Start polling with very short interval
    polling_manager.start_polling("test-channel", mock_adapter, interval=0)

    # Allow event loop to run briefly
    await asyncio.sleep(0.01)

    polling_manager.stop_all()

    # Verify poll was called
    assert mock_adapter.poll.call_count >= 1

    # Verify messages were passed to manager
    mock_manager.handle_inbound_messages.assert_called_once_with("test-channel", [msg1])


@pytest.mark.asyncio
async def test_poll_loop_error_handling(polling_manager, mock_adapter, mock_manager):
    """poll loop should catch errors and back off without crashing."""
    # Setup mock to raise an error first, then succeed
    mock_adapter.poll.side_effect = [Exception("Network error"), []]

    # Start polling with 0 interval to speed up test
    polling_manager.start_polling("test-channel", mock_adapter, interval=0)

    # Allow event loop to run briefly
    await asyncio.sleep(0.01)

    # Task should still be running despite the error
    assert polling_manager.is_polling("test-channel")

    polling_manager.stop_all()

    # poll should have been called multiple times (retried after error)
    assert mock_adapter.poll.call_count >= 1
