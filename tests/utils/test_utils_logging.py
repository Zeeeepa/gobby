"""Tests for src/utils/logging.py - Logging Utilities."""

import pytest

from gobby.utils.logging import (
    clear_request_id,
    generate_request_id,
    get_request_id,
)

pytestmark = pytest.mark.unit


class TestRequestIDFunctions:
    """Tests for request ID utility functions."""

    def test_generate_request_id(self) -> None:
        """Test that generate_request_id returns UUID string."""
        request_id = generate_request_id()
        assert isinstance(request_id, str)
        assert len(request_id) == 36  # UUID format: 8-4-4-4-12

    def test_generate_request_id_unique(self) -> None:
        """Test that each call generates unique ID."""
        ids = {generate_request_id() for _ in range(100)}
        assert len(ids) == 100  # All unique

    def test_get_request_id_default_none(self) -> None:
        """Test that default request ID is None."""
        clear_request_id()
        assert get_request_id() is None

    def test_clear_request_id(self) -> None:
        """Test clearing request ID."""
        # Note: set_request_id was removed, so we'll test with the contextvar directly
        from gobby.utils.logging import request_id_var

        request_id_var.set("test-id")
        assert get_request_id() == "test-id"

        clear_request_id()
        assert get_request_id() is None
