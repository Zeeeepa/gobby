"""
OpenTelemetry exporter factory.

Creates configured exporters for traces and metrics, and handlers for logs.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

# opentelemetry-api and sdk are in dependencies
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as OTLPGRPCSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as OTLPHTTPSpanExporter,
)
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.trace.export import ConsoleSpanExporter

if TYPE_CHECKING:
    from opentelemetry.sdk.metrics.export import MetricReader
    from opentelemetry.sdk.trace.export import SpanExporter

    from gobby.telemetry.config import TelemetrySettings


def create_exporters(
    config: TelemetrySettings,
) -> tuple[list[SpanExporter], list[MetricReader], list[logging.Handler]]:
    """
    Create and configure telemetry exporters based on settings.

    Args:
        config: TelemetrySettings instance.

    Returns:
        Tuple of (span_exporters, metric_readers, log_handlers)
    """
    span_exporters: list[SpanExporter] = []
    metric_readers: list[MetricReader] = []
    log_handlers: list[logging.Handler] = []

    # 1. Span Exporters (Tracing)
    if config.traces_enabled:
        if config.traces_to_console:
            span_exporters.append(ConsoleSpanExporter())

        if config.exporter.otlp_endpoint:
            headers = config.exporter.otlp_headers or None
            if config.exporter.otlp_protocol == "http":
                span_exporters.append(
                    OTLPHTTPSpanExporter(
                        endpoint=config.exporter.otlp_endpoint,
                        headers=headers,
                    )
                )
            else:
                span_exporters.append(
                    OTLPGRPCSpanExporter(
                        endpoint=config.exporter.otlp_endpoint,
                        headers=headers,
                    )
                )

    # 2. Metric Readers
    if config.metrics_enabled:
        if config.exporter.prometheus_enabled:
            metric_readers.append(PrometheusMetricReader())

    # 3. Log Handlers (Preserving behavior of RotatingFileHandler)
    # The plan says to preserve all 6 log file paths.
    # We create a handler for the main log file here.
    # Other log files (error, mcp, etc.) might be handled by the logging subsystem
    # using these settings, but create_exporters returns the main ones.

    log_file_path = Path(config.log_file).expanduser()
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    main_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=config.max_size_mb * 1024 * 1024,
        backupCount=config.backup_count,
    )
    log_handlers.append(main_handler)

    return span_exporters, metric_readers, log_handlers
