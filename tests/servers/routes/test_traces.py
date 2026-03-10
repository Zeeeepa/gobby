import pytest
from fastapi.testclient import TestClient

from gobby.config.app import DaemonConfig
from gobby.storage.spans import SpanStorage
from tests.servers.conftest import create_http_server


@pytest.fixture
def span_storage(temp_db):
    return SpanStorage(temp_db)


@pytest.fixture
def server(temp_db, span_storage):
    """HTTPServer with real database and span_storage."""
    srv = create_http_server(
        config=DaemonConfig(),
        database=temp_db,
        span_storage=span_storage,
    )
    return srv


@pytest.fixture
def client(server):
    return TestClient(server.app)


def test_list_traces_empty(client):
    response = client.get("/api/traces")
    assert response.status_code == 200
    data = response.json()
    assert data["traces"] == []
    assert data["total"] == 0


def test_list_traces_with_data(client, span_storage):
    span_storage.save_spans(
        [
            {"span_id": "s1", "trace_id": "t1", "name": "n1", "start_time_ns": 100},
            {"span_id": "s2", "trace_id": "t2", "name": "n2", "start_time_ns": 200},
        ]
    )

    response = client.get("/api/traces")
    assert response.status_code == 200
    data = response.json()
    assert len(data["traces"]) == 2
    # Ordered by last activity DESC (MAX(start_time_ns))
    assert data["traces"][0]["trace_id"] == "t2"
    assert data["traces"][1]["trace_id"] == "t1"


def test_get_trace_details(client, span_storage):
    span_storage.save_spans(
        [
            {"span_id": "s1", "trace_id": "t1", "name": "root", "start_time_ns": 100},
            {
                "span_id": "s2",
                "trace_id": "t1",
                "name": "child",
                "start_time_ns": 150,
                "parent_span_id": "s1",
            },
        ]
    )

    response = client.get("/api/traces/t1")
    assert response.status_code == 200
    data = response.json()
    assert data["trace_id"] == "t1"
    assert len(data["spans"]) == 2
    assert data["root_span"]["span_id"] == "s1"


def test_get_trace_not_found(client):
    response = client.get("/api/traces/missing")
    assert response.status_code == 404


def test_list_traces_by_session(client, span_storage):
    span_storage.save_spans(
        [
            {
                "span_id": "s1",
                "trace_id": "t1",
                "name": "n1",
                "start_time_ns": 100,
                "attributes": {"session_id": "sess1"},
            },
            {
                "span_id": "s2",
                "trace_id": "t2",
                "name": "n2",
                "start_time_ns": 200,
                "attributes": {"session_id": "sess2"},
            },
        ]
    )

    response = client.get("/api/traces?session_id=sess1")
    assert response.status_code == 200
    data = response.json()
    assert len(data["traces"]) == 1
    assert data["traces"][0]["trace_id"] == "t1"
