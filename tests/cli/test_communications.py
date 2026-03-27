from unittest.mock import MagicMock, patch

import httpx
import pytest
from click.testing import CliRunner

from gobby.cli.communications import comms


@pytest.fixture
def mock_daemon_client():
    with patch("gobby.cli.communications.get_daemon_client") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


def test_comms_status_success(mock_daemon_client):
    runner = CliRunner()

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "channels": [
            {
                "name": "test-channel",
                "channel_type": "telegram",
                "enabled": True,
                "status": "connected",
                "stats": {"inbound": 5, "outbound": 10},
            }
        ]
    }
    mock_daemon_client.call_http_api.return_value = mock_response

    result = runner.invoke(comms, ["status"])

    assert result.exit_code == 0
    assert "test-channel" in result.output
    assert "telegram" in result.output
    assert "5 / 10" in result.output
    mock_daemon_client.call_http_api.assert_called_once_with(
        "/api/comms/channels?status=true", method="GET"
    )


def test_comms_send_success(mock_daemon_client):
    runner = CliRunner()

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_daemon_client.call_http_api.return_value = mock_response

    result = runner.invoke(comms, ["send", "test-channel", "hello world"])

    assert result.exit_code == 0
    assert "Message sent to test-channel" in result.output
    mock_daemon_client.call_http_api.assert_called_once_with(
        "/api/comms/send",
        method="POST",
        json_data={"channel_name": "test-channel", "content": "hello world"},
    )


def test_comms_channels_list(mock_daemon_client):
    runner = CliRunner()

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "channels": [
            {"id": "cc_123", "name": "test-chan", "channel_type": "slack", "enabled": True}
        ]
    }
    mock_daemon_client.call_http_api.return_value = mock_response

    result = runner.invoke(comms, ["channels", "list"])

    assert result.exit_code == 0
    assert "test-chan" in result.output
    assert "slack" in result.output
    assert "cc_123" in result.output


def test_comms_channels_add(mock_daemon_client):
    runner = CliRunner()

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 201
    mock_daemon_client.call_http_api.return_value = mock_response

    # Simulating standard input for prompts
    result = runner.invoke(
        comms, ["channels", "add", "telegram", "my-tg"], input="mytoken\nmychatid\n"
    )

    assert result.exit_code == 0
    assert "Channel 'my-tg' added successfully" in result.output

    # Check what was posted
    mock_daemon_client.call_http_api.assert_called_once_with(
        "/api/comms/channels",
        method="POST",
        json_data={
            "name": "my-tg",
            "channel_type": "telegram",
            "config": {"bot_token": "mytoken", "chat_id": "mychatid"},
            "enabled": True,
        },
    )


def test_comms_channels_remove(mock_daemon_client):
    runner = CliRunner()

    # First response for listing
    list_response = MagicMock(spec=httpx.Response)
    list_response.status_code = 200
    list_response.json.return_value = {"channels": [{"id": "cc_123", "name": "my-tg"}]}

    # Second response for delete
    delete_response = MagicMock(spec=httpx.Response)
    delete_response.status_code = 204

    mock_daemon_client.call_http_api.side_effect = [list_response, delete_response]

    result = runner.invoke(comms, ["channels", "remove", "my-tg"], input="y\n")

    assert result.exit_code == 0
    assert "removed successfully" in result.output
    assert mock_daemon_client.call_http_api.call_count == 2
    mock_daemon_client.call_http_api.assert_any_call("/api/comms/channels", method="GET")
    mock_daemon_client.call_http_api.assert_any_call("/api/comms/channels/cc_123", method="DELETE")
