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
