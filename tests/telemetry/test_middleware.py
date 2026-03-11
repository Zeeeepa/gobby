"""
Tests for TelemetryMiddleware.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from gobby.telemetry.instruments import TelemetryMetrics
from gobby.telemetry.middleware import TelemetryMiddleware


@pytest.fixture
def meter_provider():
    """Setup a fresh MeterProvider with an InMemoryMetricReader."""
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    return provider, reader


@pytest.fixture
def metrics_collector(meter_provider):
    """Setup a fresh TelemetryMetrics instance and patch the singleton getter."""
    provider, _ = meter_provider
    meter = provider.get_meter("test-meter")
    collector = TelemetryMetrics(meter)

    with patch("gobby.telemetry.middleware.get_telemetry_metrics", return_value=collector):
        yield collector


@pytest.fixture
def app(metrics_collector):
    """Create a FastAPI app with TelemetryMiddleware."""
    app = FastAPI()
    app.add_middleware(TelemetryMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    @app.get("/error")
    async def error_endpoint():
        raise ValueError("Test error")

    return app


def test_middleware_records_request(app, meter_provider, metrics_collector):
    _, reader = meter_provider
    client = TestClient(app)

    response = client.get("/test")
    assert response.status_code == 200

    # Check OTel metrics
    data = reader.get_metrics_data()
    assert data is not None

    metrics_found = {}
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                metrics_found[metric.name] = metric

    assert "http_requests_total" in metrics_found

    # Check attributes
    dp = metrics_found["http_requests_total"].data.data_points[0]
    assert dp.attributes["http.method"] == "GET"
    assert dp.attributes["http.target"] == "/test"
    assert dp.attributes["http.status_code"] == "200"

    # Check internal tracking
    all_metrics = metrics_collector.get_all_metrics()
    assert all_metrics["counters"]["http_requests_total"]["value"] == 1


def test_middleware_records_error(app, meter_provider, metrics_collector):
    _, reader = meter_provider
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/error")
    assert response.status_code == 500

    # Check OTel metrics
    data = reader.get_metrics_data()
    assert data is not None

    metrics_found = {}
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                metrics_found[metric.name] = metric

    assert "http_requests_errors_total" in metrics_found

    # Check attributes
    dp = metrics_found["http_requests_errors_total"].data.data_points[0]
    assert dp.attributes["http.method"] == "GET"
    assert dp.attributes["http.target"] == "/error"
    assert dp.attributes["http.status_code"] == "500"

    # Check internal tracking
    all_metrics = metrics_collector.get_all_metrics()
    assert all_metrics["counters"]["http_requests_errors_total"]["value"] == 1


def test_middleware_extracts_headers(app, meter_provider, metrics_collector):
    _, reader = meter_provider
    client = TestClient(app)

    client.get("/test", headers={"X-Session-ID": "sess-123", "X-Project-ID": "proj-456"})

    data = reader.get_metrics_data()
    assert data is not None

    found = False
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == "http_requests_total":
                    dp = metric.data.data_points[0]
                    assert dp.attributes["session_id"] == "sess-123"
                    assert dp.attributes["project_id"] == "proj-456"
                    found = True
    assert found
