from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from gobby.communications.models import ChannelConfig, CommsMessage
from gobby.config.app import DaemonConfig
from tests.servers.conftest import create_http_server


@pytest.fixture
def comms_manager():
    manager = MagicMock()
    manager.handle_inbound = AsyncMock(return_value=[])
    manager.add_channel = AsyncMock()
    manager.remove_channel = AsyncMock()
    manager._store = MagicMock()

    # Mock some store methods
    manager.list_channels.return_value = []
    manager.get_channel_status.return_value = {"status": "active"}

    return manager


@pytest.fixture
def server(comms_manager):
    """HTTPServer with mocked comms manager."""
    config = DaemonConfig()
    config.communications.enabled = True

    srv = create_http_server(config=config)
    srv.services.communications_manager = comms_manager
    return srv


@pytest.fixture
def client(server):
    return TestClient(server.app)


def test_receive_webhook_ok(client, comms_manager):
    comms_manager.handle_inbound.return_value = [
        CommsMessage(id="msg1", channel_id="ch1", direction="inbound", content="hello", created_at="2023-01-01T00:00:00Z")
    ]
    response = client.post("/api/comms/webhooks/slack", json={"text": "hello"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "messages": 1}
    comms_manager.handle_inbound.assert_called_once()


def test_receive_webhook_url_verification(client, comms_manager):
    # Setup the mock to return a url_verification message
    msg = CommsMessage(
        id="msg1",
        channel_id="ch1",
        direction="inbound",
        content="challenge_token",
        content_type="url_verification",
        created_at="2023-01-01T00:00:00Z"
    )
    comms_manager.handle_inbound.return_value = [msg]

    response = client.post("/api/comms/webhooks/slack", json={"type": "url_verification", "challenge": "challenge_token"})
    assert response.status_code == 200
    assert response.text == "challenge_token"


def test_verify_webhook_get(client):
    response = client.get("/api/comms/webhooks/teams?validationToken=token123")
    assert response.status_code == 200
    assert response.text == "token123"

    response = client.get("/api/comms/webhooks/slack?challenge=chal123")
    assert response.status_code == 200
    assert response.text == "chal123"


def test_list_channels(client, comms_manager):
    ch = ChannelConfig(
        id="ch1", channel_type="slack", name="myslack", enabled=True,
        config_json={}, created_at="2023-01-01T00:00:00Z", updated_at="2023-01-01T00:00:00Z"
    )
    comms_manager.list_channels.return_value = [ch]

    response = client.get("/api/comms/channels")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == "ch1"


def test_create_channel(client, comms_manager):
    ch = ChannelConfig(
        id="ch1", channel_type="slack", name="myslack", enabled=True,
        config_json={"foo": "bar"}, created_at="2023-01-01T00:00:00Z", updated_at="2023-01-01T00:00:00Z"
    )
    comms_manager.add_channel.return_value = ch

    response = client.post("/api/comms/channels", json={
        "channel_type": "slack",
        "name": "myslack",
        "config": {"foo": "bar"}
    })

    assert response.status_code == 200
    assert response.json()["id"] == "ch1"
    comms_manager.add_channel.assert_called_once()


def test_update_channel(client, comms_manager):
    ch = ChannelConfig(
        id="ch1", channel_type="slack", name="myslack", enabled=True,
        config_json={}, created_at="2023-01-01T00:00:00Z", updated_at="2023-01-01T00:00:00Z"
    )
    comms_manager._store.get_channel.return_value = ch
    comms_manager._store.update_channel.return_value = ch

    response = client.put("/api/comms/channels/ch1", json={
        "config": {"foo": "baz"},
        "enabled": False
    })

    assert response.status_code == 200
    assert response.json()["id"] == "ch1"
    comms_manager._store.update_channel.assert_called_once_with(
        channel_id="ch1", config_json={"foo": "baz"}, enabled=False
    )


def test_remove_channel(client, comms_manager):
    ch = ChannelConfig(
        id="ch1", channel_type="slack", name="myslack", enabled=True,
        config_json={}, created_at="2023-01-01T00:00:00Z", updated_at="2023-01-01T00:00:00Z"
    )
    comms_manager._store.get_channel.return_value = ch

    response = client.delete("/api/comms/channels/ch1")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    comms_manager.remove_channel.assert_called_once_with("myslack")


def test_get_channel_status(client, comms_manager):
    ch = ChannelConfig(
        id="ch1", channel_type="slack", name="myslack", enabled=True,
        config_json={}, created_at="2023-01-01T00:00:00Z", updated_at="2023-01-01T00:00:00Z"
    )
    comms_manager._store.get_channel.return_value = ch
    comms_manager.get_channel_status.return_value = {"name": "myslack", "status": "active"}

    response = client.get("/api/comms/channels/ch1/status")
    assert response.status_code == 200
    assert response.json()["status"] == "active"


def test_list_messages(client, comms_manager):
    msg = CommsMessage(
        id="msg1", channel_id="ch1", direction="outbound", content="test", created_at="2023-01-01T00:00:00Z"
    )
    comms_manager._store.list_messages.return_value = [msg]

    response = client.get("/api/comms/messages?channel_id=ch1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "msg1"
    comms_manager._store.list_messages.assert_called_once_with(
        channel_id="ch1", session_id=None, direction=None, limit=50, offset=0
    )
