"""Tests for InternalToolRegistry schema generation, especially with stringified annotations."""

from __future__ import annotations

from typing import Any

import pytest

from gobby.mcp_proxy.tools.internal import InternalToolRegistry, _get_json_schema_type

pytestmark = pytest.mark.unit


# --- _get_json_schema_type tests ---


def test_basic_types() -> None:
    assert _get_json_schema_type(str) == "string"
    assert _get_json_schema_type(int) == "integer"
    assert _get_json_schema_type(float) == "number"
    assert _get_json_schema_type(bool) == "boolean"
    assert _get_json_schema_type(dict) == "object"
    assert _get_json_schema_type(list) == "array"


def test_generic_types() -> None:
    assert _get_json_schema_type(dict[str, Any]) == "object"
    assert _get_json_schema_type(list[str]) == "array"


def test_union_with_none() -> None:
    assert _get_json_schema_type(str | None) == "string"
    assert _get_json_schema_type(float | None) == "number"
    assert _get_json_schema_type(list[str] | None) == "array"
    assert _get_json_schema_type(dict[str, Any] | None) == "object"


def test_empty_annotation() -> None:
    import inspect

    assert _get_json_schema_type(inspect.Parameter.empty) == "string"


# --- Decorator schema generation with `from __future__ import annotations` ---


def test_decorator_resolves_stringified_annotations() -> None:
    """The decorator must use get_type_hints() to resolve string annotations."""
    registry = InternalToolRegistry(name="test-registry")

    @registry.tool(name="test_tool", description="A test tool")
    def test_tool(
        name: str,
        count: int,
        score: float,
        enabled: bool,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {}

    schema = registry.get_schema("test_tool")
    assert schema is not None
    props = schema["inputSchema"]["properties"]

    assert props["name"]["type"] == "string"
    assert props["count"]["type"] == "integer"
    assert props["score"]["type"] == "number"
    assert props["enabled"]["type"] == "boolean"
    assert props["tags"]["type"] == "array"
    assert props["metadata"]["type"] == "object"


# --- _coerce_args tests ---


def test_coerce_integer_from_string() -> None:
    """String values should be coerced to int when schema says integer."""
    schema = {"properties": {"limit": {"type": "integer"}}}
    result = InternalToolRegistry._coerce_args({"limit": "5"}, schema)
    assert result["limit"] == 5
    assert isinstance(result["limit"], int)


def test_coerce_number_from_string() -> None:
    """String values should be coerced to float when schema says number."""
    schema = {"properties": {"threshold": {"type": "number"}}}
    result = InternalToolRegistry._coerce_args({"threshold": "0.7"}, schema)
    assert result["threshold"] == 0.7
    assert isinstance(result["threshold"], float)


def test_coerce_boolean_from_string() -> None:
    """String values should be coerced to bool when schema says boolean."""
    schema = {"properties": {"enabled": {"type": "boolean"}}}
    assert InternalToolRegistry._coerce_args({"enabled": "true"}, schema)["enabled"] is True
    assert InternalToolRegistry._coerce_args({"enabled": "false"}, schema)["enabled"] is False
    assert InternalToolRegistry._coerce_args({"enabled": "1"}, schema)["enabled"] is True
    assert InternalToolRegistry._coerce_args({"enabled": "0"}, schema)["enabled"] is False


def test_coerce_array_from_csv_string() -> None:
    """Comma-separated string should be coerced to list when schema says array."""
    schema = {"properties": {"tags": {"type": "array"}}}
    result = InternalToolRegistry._coerce_args({"tags": "a,b,c"}, schema)
    assert result["tags"] == ["a", "b", "c"]


def test_coerce_array_from_json_string() -> None:
    """JSON array string should be coerced to list when schema says array."""
    schema = {"properties": {"tags": {"type": "array"}}}
    result = InternalToolRegistry._coerce_args({"tags": '["a", "b"]'}, schema)
    assert result["tags"] == ["a", "b"]


def test_coerce_skips_non_string_values() -> None:
    """Values that are already the correct type should pass through."""
    schema = {"properties": {"limit": {"type": "integer"}, "tags": {"type": "array"}}}
    result = InternalToolRegistry._coerce_args({"limit": 10, "tags": ["a"]}, schema)
    assert result["limit"] == 10
    assert result["tags"] == ["a"]


def test_coerce_skips_string_type() -> None:
    """String values for string-typed params should not be modified."""
    schema = {"properties": {"query": {"type": "string"}}}
    result = InternalToolRegistry._coerce_args({"query": "hello"}, schema)
    assert result["query"] == "hello"


def test_coerce_handles_invalid_value_gracefully() -> None:
    """Invalid values should pass through without raising."""
    schema = {"properties": {"limit": {"type": "integer"}}}
    result = InternalToolRegistry._coerce_args({"limit": "not_a_number"}, schema)
    assert result["limit"] == "not_a_number"


@pytest.mark.asyncio
async def test_call_coerces_string_args_to_declared_types() -> None:
    """End-to-end: call() should coerce string args before invoking the function."""
    registry = InternalToolRegistry(name="test-registry")

    @registry.tool(name="search", description="Search")
    def search(query: str, limit: int = 10, threshold: float = 0.5) -> dict[str, Any]:
        return {"query": query, "limit": limit, "threshold": threshold}

    result = await registry.call("search", {"query": "test", "limit": "5", "threshold": "0.7"})
    assert result["limit"] == 5
    assert isinstance(result["limit"], int)
    assert result["threshold"] == 0.7
    assert isinstance(result["threshold"], float)


def test_decorator_required_vs_optional() -> None:
    """Parameters without defaults should be required."""
    registry = InternalToolRegistry(name="test-registry")

    @registry.tool(name="test_tool", description="A test tool")
    def test_tool(
        required_param: str,
        optional_param: str = "default",
    ) -> str:
        return ""

    schema = registry.get_schema("test_tool")
    assert schema is not None
    assert "required_param" in schema["inputSchema"]["required"]
    assert "optional_param" not in schema["inputSchema"]["required"]
