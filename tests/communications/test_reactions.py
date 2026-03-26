from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.communications.reactions import ReactionHandler


@pytest.mark.asyncio
async def test_handle_reaction_approve():
    store = MagicMock()
    service_container = MagicMock()
    service_container.pipeline_execution_manager = MagicMock()
    service_container.pipeline_execution_manager.approve_step = AsyncMock()

    handler = ReactionHandler(store, service_container)

    # Mock message
    mock_message = MagicMock()
    mock_message.channel_id = "test_channel"
    mock_message.metadata_json = {"approval_context": {"run_id": "run_123", "step_id": "step_456"}}
    store.get_message_by_platform_id.return_value = mock_message

    # Mock identity
    mock_identity = MagicMock()
    mock_identity.session_id = "session_1"
    store.get_identity_by_external.return_value = mock_identity

    await handler.handle_reaction("test_channel", "msg_123", "+1", "user_123")

    store.get_message_by_platform_id.assert_called_with("test_channel", "msg_123")
    store.get_identity_by_external.assert_called_with("test_channel", "user_123")
    service_container.pipeline_execution_manager.approve_step.assert_awaited_once_with(
        "run_123", "step_456", "session_1"
    )


@pytest.mark.asyncio
async def test_handle_reaction_reject():
    store = MagicMock()
    service_container = MagicMock()
    service_container.pipeline_execution_manager = MagicMock()
    service_container.pipeline_execution_manager.reject_step = AsyncMock()

    handler = ReactionHandler(store, service_container)

    # Mock message
    mock_message = MagicMock()
    mock_message.channel_id = "test_channel"
    mock_message.metadata_json = {"approval_context": {"run_id": "run_123", "step_id": "step_456"}}
    store.get_message_by_platform_id.return_value = mock_message

    # Mock identity
    mock_identity = MagicMock()
    mock_identity.session_id = "session_1"
    store.get_identity_by_external.return_value = mock_identity

    await handler.handle_reaction("test_channel", "msg_123", "-1", "user_123")

    service_container.pipeline_execution_manager.reject_step.assert_awaited_once_with(
        "run_123", "step_456", "session_1"
    )


@pytest.mark.asyncio
async def test_handle_reaction_unknown_message():
    store = MagicMock()
    service_container = MagicMock()
    service_container.pipeline_execution_manager = AsyncMock()

    handler = ReactionHandler(store, service_container)

    store.get_message_by_platform_id.return_value = None

    await handler.handle_reaction("test_channel", "msg_123", "+1", "user_123")

    service_container.pipeline_execution_manager.approve_step.assert_not_called()
