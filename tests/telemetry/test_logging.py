import logging
from pathlib import Path

import pytest
from opentelemetry.sdk.trace import TracerProvider

from gobby.telemetry.config import TelemetrySettings
from gobby.telemetry.logging import (
    JsonOTelFormatter,
    OTelTraceFormatter,
    setup_otel_logging,
)


@pytest.fixture
def temp_log_dir(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return log_dir


@pytest.fixture
def telemetry_config(temp_log_dir):
    return TelemetrySettings(
        log_file=str(temp_log_dir / "gobby.log"),
        log_file_error=str(temp_log_dir / "gobby-error.log"),
        log_file_hook_manager=str(temp_log_dir / "hook-manager.log"),
        log_file_mcp_server=str(temp_log_dir / "mcp-server.log"),
        log_file_mcp_client=str(temp_log_dir / "mcp-client.log"),
        log_file_watchdog=str(temp_log_dir / "watchdog.log"),
        log_level="debug",
        log_format="text",
    )


def test_otel_trace_formatter_injects_trace_id():
    formatter = OTelTraceFormatter("%(trace_id)s - %(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="test message",
        args=(),
        exc_info=None,
    )

    # Without active span
    assert " - test message" in formatter.format(record)
    assert record.trace_id == "-"

    # With active span
    provider = TracerProvider()
    tracer = provider.get_tracer(__name__)
    with tracer.start_as_current_span("test-span") as span:
        trace_id = format(span.get_span_context().trace_id, "032x")
        formatted = formatter.format(record)
        assert trace_id in formatted
        assert record.trace_id == trace_id


def test_json_otel_formatter_produces_json():
    formatter = JsonOTelFormatter()
    record = logging.LogRecord(
        name="gobby.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="test message",
        args=(),
        exc_info=None,
    )

    import json

    formatted = formatter.format(record)
    data = json.loads(formatted)

    assert data["level"] == "INFO"
    assert data["message"] == "test message"
    assert data["name"] == "gobby.test"


def test_setup_otel_logging_creates_files(telemetry_config):
    setup_otel_logging(telemetry_config)

    # Check that handlers are attached to root logger
    root_logger = logging.getLogger("gobby")
    assert len(root_logger.handlers) >= 3  # main, error, otel

    # Trigger some logs
    root_logger.info("Main log message")
    root_logger.error("Error log message")

    logging.getLogger("gobby.hooks").info("Hook message")
    logging.getLogger("gobby.mcp.server").info("MCP server message")
    logging.getLogger("gobby.mcp.client").info("MCP client message")
    logging.getLogger("gobby.watchdog").info("Watchdog message")

    # Verify files exist
    assert Path(telemetry_config.log_file).exists()
    assert Path(telemetry_config.log_file_error).exists()
    assert Path(telemetry_config.log_file_hook_manager).exists()
    assert Path(telemetry_config.log_file_mcp_server).exists()
    assert Path(telemetry_config.log_file_mcp_client).exists()
    assert Path(telemetry_config.log_file_watchdog).exists()

    # Verify content
    content = Path(telemetry_config.log_file).read_text()
    assert "Main log message" in content

    error_content = Path(telemetry_config.log_file_error).read_text()
    assert "Error log message" in error_content

    hook_content = Path(telemetry_config.log_file_hook_manager).read_text()
    assert "Hook message" in hook_content


def test_setup_otel_logging_rotation(telemetry_config):
    # Set small max_size_mb for testing rotation
    telemetry_config.max_size_mb = 1  # 1MB
    telemetry_config.backup_count = 2

    setup_otel_logging(telemetry_config)

    logger = logging.getLogger("gobby")
    # Write a lot of data
    large_msg = "x" * 1024 * 100  # 100KB
    for _ in range(15):  # 1.5MB total
        logger.info(large_msg)

    # Check if rotated file exists
    assert Path(f"{telemetry_config.log_file}.1").exists()
