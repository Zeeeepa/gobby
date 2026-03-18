import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from gobby.servers.websocket.session_control import SessionControlMixin

@pytest.mark.asyncio
async def test_handle_plan_approval_request_changes_legacy_sends_mode_changed():
    """Test that request_changes in the legacy path (no pending plan) sends mode_changed."""
    
    # Create a host that implements the mixin's required attributes
    class MockHost(SessionControlMixin):
        def __init__(self):
            self._chat_sessions = {}
            self.clients = {}
            self._active_chat_tasks = {}
            self._pending_modes = {}
            self._pending_worktree_paths = {}
            self._pending_agents = {}

    host = MockHost()
    
    # Mock a session
    session = MagicMock()
    session.has_pending_plan = False
    session.chat_mode = "plan"
    
    conversation_id = "test-conv-id"
    host._chat_sessions[conversation_id] = session
    
    # Mock a websocket
    websocket = AsyncMock()
    
    # Data for request_changes
    data = {
        "type": "plan_approval_response",
        "conversation_id": conversation_id,
        "decision": "request_changes",
        "feedback": "Please fix the typo."
    }
    
    # Call the handler
    # We call it directly from the class since it's a mixin and we want to test its implementation
    await SessionControlMixin._handle_plan_approval_response(host, websocket, data)
    
    # Verify feedback was set
    session.set_plan_feedback.assert_called_once_with("Please fix the typo.")
    
    # Verify mode_changed was sent via websocket
    # THIS SHOULD FAIL BEFORE THE FIX
    websocket.send.assert_called_once()
    sent_data = json.loads(websocket.send.call_args[0][0])
    assert sent_data["type"] == "mode_changed"
    assert sent_data["conversation_id"] == conversation_id
    assert sent_data["mode"] == "plan"
    assert sent_data["reason"] == "plan_changes_requested"

@pytest.mark.asyncio
async def test_handle_plan_approval_approve_legacy_sends_mode_changed():
    """Verify existing behavior for approve (legacy path) to ensure parity."""
    
    class MockHost(SessionControlMixin):
        def __init__(self):
            self._chat_sessions = {}
            self.clients = {}
            self._active_chat_tasks = {}
            self._pending_modes = {}
            self._pending_worktree_paths = {}
            self._pending_agents = {}

    host = MockHost()
    
    session = MagicMock()
    session.has_pending_plan = False
    
    conversation_id = "test-conv-id"
    host._chat_sessions[conversation_id] = session
    
    websocket = AsyncMock()
    
    data = {
        "type": "plan_approval_response",
        "conversation_id": conversation_id,
        "decision": "approve"
    }
    
    await SessionControlMixin._handle_plan_approval_response(host, websocket, data)
    
    # Verify existing behavior
    session.approve_plan.assert_called_once()
    session.set_chat_mode.assert_called_once_with("accept_edits")
    
    websocket.send.assert_called_once()
    sent_data = json.loads(websocket.send.call_args[0][0])
    assert sent_data["type"] == "mode_changed"
    assert sent_data["mode"] == "accept_edits"
    assert sent_data["reason"] == "plan_approved"
