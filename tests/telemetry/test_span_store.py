from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import SpanContext, SpanKind, Status, StatusCode

from gobby.telemetry.span_store import GobbySpanExporter


@pytest.fixture
def mock_storage():
    return MagicMock()


@pytest.fixture
def exporter(mock_storage):
    return GobbySpanExporter(mock_storage)


def test_export_spans(exporter, mock_storage):
    # Mock a ReadableSpan
    span = MagicMock(spec=ReadableSpan)
    span.name = "test-span"
    span.context = SpanContext(
        trace_id=0x12345678123456781234567812345678, span_id=0x1234567812345678, is_remote=False
    )
    span.parent = None
    span.kind = SpanKind.INTERNAL
    span.start_time = 1000000
    span.end_time = 2000000
    span.status = Status(status_code=StatusCode.OK, description="All good")
    span.attributes = {"key": "value"}
    span.events = []

    exporter.export([span])

    assert mock_storage.save_spans.called
    saved_spans = mock_storage.save_spans.call_args[0][0]
    assert len(saved_spans) == 1
    assert saved_spans[0]["span_id"] == "1234567812345678"
    assert saved_spans[0]["trace_id"] == "12345678123456781234567812345678"
    assert saved_spans[0]["name"] == "test-span"
    assert saved_spans[0]["status"] == "OK"
    assert saved_spans[0]["attributes"] == {"key": "value"}


def test_broadcast_callback(mock_storage):
    callback = MagicMock()
    exporter = GobbySpanExporter(mock_storage, broadcast_callback=callback)

    span = MagicMock(spec=ReadableSpan)
    span.name = "test-span"
    span.context = SpanContext(trace_id=1, span_id=1, is_remote=False)
    span.parent = None
    span.kind = SpanKind.INTERNAL
    span.start_time = 100
    span.end_time = 200
    span.status = Status(status_code=StatusCode.OK)
    span.attributes = {}
    span.events = []

    exporter.export([span])

    assert callback.called
    event = callback.call_args[0][0]
    assert event["type"] == "trace_event"
    assert event["trace_id"] == "00000000000000000000000000000001"
