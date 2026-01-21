from unittest.mock import MagicMock

import pytest
from textual.app import App


@pytest.fixture
def mock_api_client():
    """Mock GobbyAPIClient."""
    client = MagicMock()
    client.base_url = "http://localhost:8000"
    return client


@pytest.fixture
def mock_ws_client():
    """Mock GobbyWebSocketClient."""
    return MagicMock()


@pytest.fixture
def app():
    """Test app instance."""
    return App()
