"""Tests for src/utils/logging.py - Logging Utilities."""

import logging
from typing import Any, cast
from unittest.mock import MagicMock, patch

from gobby.utils.logging import (
    ContextLogger,
    ExtraFieldsFormatter,
    RequestIDFilter,
    clear_request_id,
    generate_request_id,
    get_context_logger,
    get_mcp_client_logger,
    get_mcp_server_logger,
    get_request_id,
    set_request_id,
    setup_file_logging,
    setup_mcp_logging,
)


class TestRequestIDFunctions:
    """Tests for request ID utility functions."""

    def test_generate_request_id(self):
        """Test that generate_request_id returns UUID string."""
        request_id = generate_request_id()
        assert isinstance(request_id, str)
        assert len(request_id) == 36  # UUID format: 8-4-4-4-12

    def test_generate_request_id_unique(self):
        """Test that each call generates unique ID."""
        ids = {generate_request_id() for _ in range(100)}
        assert len(ids) == 100  # All unique

    def test_set_request_id_with_value(self):
        """Test setting specific request ID."""
        test_id = "test-request-123"
        result = set_request_id(test_id)

        assert result == test_id
        assert get_request_id() == test_id

        # Cleanup
        clear_request_id()

    def test_set_request_id_generates_new(self):
        """Test that None generates new ID."""
        result = set_request_id(None)

        assert result is not None
        assert len(result) == 36
        assert get_request_id() == result

        # Cleanup
        clear_request_id()

    def test_get_request_id_default_none(self):
        """Test that default request ID is None."""
        clear_request_id()
        assert get_request_id() is None

    def test_clear_request_id(self):
        """Test clearing request ID."""
        set_request_id("test-id")
        assert get_request_id() == "test-id"

        clear_request_id()
        assert get_request_id() is None


class TestRequestIDFilter:
    """Tests for RequestIDFilter."""

    def test_filter_adds_request_id(self):
        """Test that filter adds request_id to record."""
        set_request_id("test-filter-id")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )

        filter_obj = RequestIDFilter()
        result = filter_obj.filter(record)

        assert result is True
        assert cast(Any, record).request_id == "test-filter-id"

        clear_request_id()

    def test_filter_adds_dash_when_no_id(self):
        """Test that filter adds '-' when no request ID set."""
        clear_request_id()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )

        filter_obj = RequestIDFilter()
        filter_obj.filter(record)

        assert cast(Any, record).request_id == "-"


class TestContextLogger:
    """Tests for ContextLogger adapter."""

    def test_process_adds_request_id(self):
        """Test that process adds request_id to extra."""
        set_request_id("context-logger-id")

        base_logger = logging.getLogger("test.context")
        adapter = ContextLogger(base_logger, {})

        msg, kwargs = adapter.process("test message", {})

        assert kwargs["extra"]["request_id"] == "context-logger-id"

        clear_request_id()

    def test_process_merges_extra(self):
        """Test that process merges adapter extra with kwargs extra."""
        base_logger = logging.getLogger("test.context2")
        adapter = ContextLogger(base_logger, {"component": "test"})

        msg, kwargs = adapter.process("test message", {"extra": {"custom": "value"}})

        assert kwargs["extra"]["component"] == "test"
        assert kwargs["extra"]["custom"] == "value"

    def test_get_context_logger(self):
        """Test get_context_logger creates ContextLogger."""
        logger = get_context_logger("test.module", {"extra_key": "extra_value"})

        assert isinstance(logger, ContextLogger)
        assert logger.extra is not None
        assert logger.extra["extra_key"] == "extra_value"


class TestExtraFieldsFormatter:
    """Tests for ExtraFieldsFormatter."""

    def test_format_strips_gobby_prefix(self):
        """Test that gobby. prefix is stripped from logger name."""
        formatter = ExtraFieldsFormatter("%(short_name)s - %(message)s")

        record = logging.LogRecord(
            name="gobby.http_server",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )

        formatter.format(record)
        assert cast(Any, record).short_name == "http_server"

    def test_format_no_prefix(self):
        """Test formatting without gobby prefix."""
        formatter = ExtraFieldsFormatter("%(short_name)s - %(message)s")

        record = logging.LogRecord(
            name="other.module",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )

        formatter.format(record)

        assert cast(Any, record).short_name == "other.module"

    def test_format_includes_extra_fields(self):
        """Test that extra fields are included in output."""
        formatter = ExtraFieldsFormatter("%(message)s")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )
        record.custom_field = "custom_value"
        record.another_field = 123

        result = formatter.format(record)

        assert "custom_field=custom_value" in result
        assert "another_field=123" in result

    def test_format_excludes_standard_attrs(self):
        """Test that standard log attributes are excluded from extra."""
        formatter = ExtraFieldsFormatter("%(message)s")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)

        # Standard attrs should not appear in extra section
        assert "| name=" not in result
        assert "| levelname=" not in result
        assert "| pathname=" not in result


class TestSetupFileLogging:
    """Tests for setup_file_logging function."""

    def test_setup_creates_log_directory(self, tmp_path):
        """Test that setup creates log directory if needed."""
        mock_config = MagicMock()
        mock_config.logging.client = str(tmp_path / "logs" / "gobby.log")
        mock_config.logging.client_error = str(tmp_path / "logs" / "gobby-error.log")
        mock_config.logging.max_size_mb = 10
        mock_config.logging.backup_count = 3
        mock_config.logging.level = "INFO"
        mock_config.logging.format = "text"

        with patch("gobby.config.app.load_config", return_value=mock_config):
            setup_file_logging(verbose=False)

        assert (tmp_path / "logs").exists()

    def test_setup_verbose_mode(self, tmp_path):
        """Test that verbose mode sets DEBUG level."""
        mock_config = MagicMock()
        mock_config.logging.client = str(tmp_path / "logs" / "gobby.log")
        mock_config.logging.client_error = str(tmp_path / "logs" / "gobby-error.log")
        mock_config.logging.max_size_mb = 10
        mock_config.logging.backup_count = 3
        mock_config.logging.level = "INFO"
        mock_config.logging.format = "text"

        with patch("gobby.config.app.load_config", return_value=mock_config):
            setup_file_logging(verbose=True)

        pkg_logger = logging.getLogger("gobby")
        assert pkg_logger.level == logging.DEBUG

    def test_setup_json_format(self, tmp_path):
        """Test JSON format configuration."""
        mock_config = MagicMock()
        mock_config.logging.client = str(tmp_path / "logs" / "gobby.log")
        mock_config.logging.client_error = str(tmp_path / "logs" / "gobby-error.log")
        mock_config.logging.max_size_mb = 10
        mock_config.logging.backup_count = 3
        mock_config.logging.level = "INFO"
        mock_config.logging.format = "json"

        with patch("gobby.config.app.load_config", return_value=mock_config):
            setup_file_logging(verbose=False)

        # Verify logger was configured (handlers added)
        pkg_logger = logging.getLogger("gobby")
        assert len(pkg_logger.handlers) > 0


class TestSetupMCPLogging:
    """Tests for setup_mcp_logging function."""

    def test_setup_returns_two_loggers(self, tmp_path):
        """Test that setup returns server and client loggers."""
        mock_config = MagicMock()
        mock_config.logging.mcp_server = str(tmp_path / "logs" / "mcp-server.log")
        mock_config.logging.mcp_client = str(tmp_path / "logs" / "mcp-client.log")
        mock_config.logging.max_size_mb = 10
        mock_config.logging.backup_count = 3
        mock_config.logging.level = "INFO"
        mock_config.logging.format = "text"

        with patch("gobby.config.app.load_config", return_value=mock_config):
            server_logger, client_logger = setup_mcp_logging(verbose=False)

        assert server_logger.name == "gobby.mcp.server"
        assert client_logger.name == "gobby.mcp.client"

    def test_setup_mcp_verbose(self, tmp_path):
        """Test MCP logging in verbose mode."""
        mock_config = MagicMock()
        mock_config.logging.mcp_server = str(tmp_path / "logs" / "mcp-server.log")
        mock_config.logging.mcp_client = str(tmp_path / "logs" / "mcp-client.log")
        mock_config.logging.max_size_mb = 10
        mock_config.logging.backup_count = 3
        mock_config.logging.level = "INFO"
        mock_config.logging.format = "text"

        with patch("gobby.config.app.load_config", return_value=mock_config):
            server_logger, client_logger = setup_mcp_logging(verbose=True)

        assert server_logger.level == logging.DEBUG
        assert client_logger.level == logging.DEBUG


class TestGetMCPLoggers:
    """Tests for get_mcp_server_logger and get_mcp_client_logger."""

    def test_get_mcp_server_logger(self):
        """Test getting MCP server logger."""
        logger = get_mcp_server_logger()
        assert logger.name == "gobby.mcp.server"

    def test_get_mcp_client_logger(self):
        """Test getting MCP client logger."""
        logger = get_mcp_client_logger()
        assert logger.name == "gobby.mcp.client"

    def test_loggers_are_same_instance(self):
        """Test that repeated calls return same logger instance."""
        logger1 = get_mcp_server_logger()
        logger2 = get_mcp_server_logger()
        assert logger1 is logger2
