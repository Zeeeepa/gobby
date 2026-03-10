"""
Tests for telemetry exporters factory.
"""

import logging
from logging.handlers import RotatingFileHandler

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.trace.export import ConsoleSpanExporter

from gobby.telemetry.config import TelemetrySettings
from gobby.telemetry.exporters import create_exporters


def test_create_exporters_defaults() -> None:
    """Test create_exporters with default settings."""
    config = TelemetrySettings()
    span_exporters, metric_readers, log_handlers = create_exporters(config)

    # Defaults: traces disabled, metrics enabled (Prometheus), 1 log handler
    assert len(span_exporters) == 0
    assert len(metric_readers) == 1
    assert isinstance(metric_readers[0], PrometheusMetricReader)
    assert len(log_handlers) == 1
    assert isinstance(log_handlers[0], RotatingFileHandler)


def test_create_exporters_traces_enabled() -> None:
    """Test create_exporters with traces enabled."""
    config = TelemetrySettings(
        traces_enabled=True,
        traces_to_console=True,
        exporter={"otlp_endpoint": "http://localhost:4317"}
    )
    span_exporters, _, _ = create_exporters(config)

    assert len(span_exporters) == 2
    assert any(isinstance(e, ConsoleSpanExporter) for e in span_exporters)
    assert any(isinstance(e, OTLPSpanExporter) for e in span_exporters)


def test_create_exporters_metrics_disabled() -> None:
    """Test create_exporters with metrics disabled."""
    config = TelemetrySettings(metrics_enabled=False)
    _, metric_readers, _ = create_exporters(config)
    assert len(metric_readers) == 0


def test_create_exporters_prometheus_disabled() -> None:
    """Test create_exporters with prometheus disabled."""
    config = TelemetrySettings(
        metrics_enabled=True,
        exporter={"prometheus_enabled": False}
    )
    _, metric_readers, _ = create_exporters(config)
    assert len(metric_readers) == 0
