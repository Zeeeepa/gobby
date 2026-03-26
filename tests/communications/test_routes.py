from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gobby.communications.models import ChannelConfig, CommsMessage
from gobby.servers.routes.communications import create_communications_router


@pytest.fixture
def mock_server():
    server = MagicMock()
    server.services = MagicMock()
    server.services.communications_manager = MagicMock()

    # Manager mocks
    manager = server.services.communications_manager
    manager.handle_inbound = AsyncMock()
    manager.add_channel = AsyncMock()
    manager.remove_channel = AsyncMock()

    # Store mocks
    manager._store = MagicMock()

    return server


@pytest.fixture
def client(mock_server):
    app = FastAPI()
    router = create_communications_router(mock_server)
    app.include_router(router)
    return TestClient(app)


def test_receive_webhook(client, mock_server):
    mock_server.services.communications_manager.handle_inbound.return_value = []

    response = client.post("/api/comms/webhooks/slack", json={"text": "hello"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "messages": 0}


def test_receive_webhook_challenge(client, mock_server):
    dt = datetime.now(UTC)
    msg = CommsMessage(
        id="1", channel_id="ch_1", direction="inbound", content="chal123", created_at=dt
    )
    msg.content_type = "url_verification"
    mock_server.services.communications_manager.handle_inbound.return_value = [msg]

    response = client.post(
        "/api/comms/webhooks/slack", json={"type": "url_verification", "challenge": "chal123"}
    )
    assert response.status_code == 200
    assert response.text == "chal123"


def test_verify_webhook(client):
    response = client.get("/api/comms/webhooks/slack?challenge=chal123")
    assert response.status_code == 200
    assert response.text == "chal123"


def test_list_channels(client, mock_server):
    dt = datetime.now(UTC)
    ch = ChannelConfig(
        id="ch_1",
        channel_type="slack",
        name="slack1",
        enabled=True,
        config_json={},
        created_at=dt,
        updated_at=dt,
    )
    mock_server.services.communications_manager.list_channels.return_value = [ch]

    response = client.get("/api/comms/channels")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_create_channel(client, mock_server):
    dt = datetime.now(UTC)
    ch = ChannelConfig(
        id="ch_1",
        channel_type="slack",
        name="slack1",
        enabled=True,
        config_json={},
        created_at=dt,
        updated_at=dt,
    )
    mock_server.services.communications_manager.add_channel.return_value = ch

    response = client.post(
        "/api/comms/channels", json={"channel_type": "slack", "name": "slack1", "config": {}}
    )
    assert response.status_code == 200
    assert response.json()["id"] == "ch_1"


def test_update_channel(client, mock_server):
    dt = datetime.now(UTC)
    ch = ChannelConfig(
        id="ch_1",
        channel_type="slack",
        name="slack1",
        enabled=True,
        config_json={},
        created_at=dt,
        updated_at=dt,
    )
    mock_server.services.communications_manager._store.get_channel.return_value = ch
    mock_server.services.communications_manager._store.update_channel.return_value = ch

    response = client.put("/api/comms/channels/ch_1", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["id"] == "ch_1"


def test_remove_channel(client, mock_server):
    dt = datetime.now(UTC)
    ch = ChannelConfig(
        id="ch_1",
        channel_type="slack",
        name="slack1",
        enabled=True,
        config_json={},
        created_at=dt,
        updated_at=dt,
    )
    mock_server.services.communications_manager._store.get_channel.return_value = ch

    response = client.delete("/api/comms/channels/ch_1")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "deleted": "ch_1"}


def test_get_channel_status(client, mock_server):
    dt = datetime.now(UTC)
    ch = ChannelConfig(
        id="ch_1",
        channel_type="slack",
        name="slack1",
        enabled=True,
        config_json={},
        created_at=dt,
        updated_at=dt,
    )
    mock_server.services.communications_manager._store.get_channel.return_value = ch
    mock_server.services.communications_manager.get_channel_status.return_value = {"status": "ok"}

    response = client.get("/api/comms/channels/ch_1/status")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_messages(client, mock_server):
    dt = datetime.now(UTC)
    msg = CommsMessage(
        id="msg_1", channel_id="ch_1", direction="outbound", content="test", created_at=dt
    )
    mock_server.services.communications_manager._store.list_messages.return_value = [msg]

    response = client.get("/api/comms/messages")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == "msg_1"
