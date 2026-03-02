"""Tests for workflows/mcp_actions.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


# --- _has_template_syntax ---


def test_has_template_syntax_string() -> None:
    from gobby.workflows.mcp_actions import _has_template_syntax

    assert _has_template_syntax("{{ var }}") is True
    assert _has_template_syntax("plain") is False


def test_has_template_syntax_dict() -> None:
    from gobby.workflows.mcp_actions import _has_template_syntax

    assert _has_template_syntax({"key": "{{ x }}"}) is True
    assert _has_template_syntax({"key": "plain"}) is False


def test_has_template_syntax_list() -> None:
    from gobby.workflows.mcp_actions import _has_template_syntax

    assert _has_template_syntax(["{{ x }}", "plain"]) is True
    assert _has_template_syntax(["a", "b"]) is False


def test_has_template_syntax_other_types() -> None:
    from gobby.workflows.mcp_actions import _has_template_syntax

    assert _has_template_syntax(42) is False
    assert _has_template_syntax(None) is False


# --- _render_value / _render_arguments ---


def test_render_value_string_template() -> None:
    from gobby.workflows.mcp_actions import _render_value

    engine = MagicMock()
    engine.render.return_value = "resolved"
    result = _render_value("{{ x }}", engine, {})
    assert result == "resolved"


def test_render_value_plain_string() -> None:
    from gobby.workflows.mcp_actions import _render_value

    result = _render_value("plain", MagicMock(), {})
    assert result == "plain"


def test_render_value_dict() -> None:
    from gobby.workflows.mcp_actions import _render_value

    engine = MagicMock()
    engine.render.return_value = "val"
    result = _render_value({"k": "{{ v }}"}, engine, {})
    assert isinstance(result, dict)


def test_render_value_list() -> None:
    from gobby.workflows.mcp_actions import _render_value

    engine = MagicMock()
    engine.render.return_value = "val"
    result = _render_value(["{{ x }}"], engine, {})
    assert isinstance(result, list)
    assert result[0] == "val"


def test_render_value_non_template() -> None:
    from gobby.workflows.mcp_actions import _render_value

    result = _render_value(42, MagicMock(), {})
    assert result == 42


def test_render_arguments() -> None:
    from gobby.workflows.mcp_actions import _render_arguments

    engine = MagicMock()
    engine.render.return_value = "rendered"
    result = _render_arguments({"a": "{{ x }}", "b": "plain"}, engine, {})
    assert result["a"] == "rendered"
    assert result["b"] == "plain"


# --- call_mcp_tool ---


@pytest.mark.asyncio
async def test_call_mcp_tool_success() -> None:
    from gobby.workflows.mcp_actions import call_mcp_tool

    proxy = MagicMock()
    proxy.call_tool = AsyncMock(return_value={"data": "ok"})
    getter = MagicMock(return_value=proxy)
    state = MagicMock()
    state.variables = {}

    result = await call_mcp_tool(getter, state, "server", "tool", {"arg": "val"}, "result_var")
    assert result["result"] == {"data": "ok"}
    assert result["stored_as"] == "result_var"
    assert state.variables["result_var"] == {"data": "ok"}


@pytest.mark.asyncio
async def test_call_mcp_tool_no_server_name() -> None:
    from gobby.workflows.mcp_actions import call_mcp_tool

    result = await call_mcp_tool(MagicMock(), MagicMock(), None, "tool")
    assert result == {"error": "Missing server_name or tool_name"}


@pytest.mark.asyncio
async def test_call_mcp_tool_no_tool_name() -> None:
    from gobby.workflows.mcp_actions import call_mcp_tool

    result = await call_mcp_tool(MagicMock(), MagicMock(), "server", None)
    assert result == {"error": "Missing server_name or tool_name"}


@pytest.mark.asyncio
async def test_call_mcp_tool_no_getter() -> None:
    from gobby.workflows.mcp_actions import call_mcp_tool

    result = await call_mcp_tool(None, MagicMock(), "server", "tool")
    assert result == {"error": "Tool proxy not available"}


@pytest.mark.asyncio
async def test_call_mcp_tool_getter_returns_none() -> None:
    from gobby.workflows.mcp_actions import call_mcp_tool

    getter = MagicMock(return_value=None)
    result = await call_mcp_tool(getter, MagicMock(), "server", "tool")
    assert result == {"error": "Tool proxy not available"}


@pytest.mark.asyncio
async def test_call_mcp_tool_error() -> None:
    from gobby.workflows.mcp_actions import call_mcp_tool

    proxy = MagicMock()
    proxy.call_tool = AsyncMock(side_effect=RuntimeError("timeout"))
    getter = MagicMock(return_value=proxy)

    result = await call_mcp_tool(getter, MagicMock(), "server", "tool")
    assert "error" in result
    assert "timeout" in result["error"]


@pytest.mark.asyncio
async def test_call_mcp_tool_no_output_as() -> None:
    from gobby.workflows.mcp_actions import call_mcp_tool

    proxy = MagicMock()
    proxy.call_tool = AsyncMock(return_value={"data": "ok"})
    getter = MagicMock(return_value=proxy)

    result = await call_mcp_tool(getter, MagicMock(), "server", "tool", {}, None)
    assert result["stored_as"] is None


@pytest.mark.asyncio
async def test_call_mcp_tool_output_as_creates_variables() -> None:
    from gobby.workflows.mcp_actions import call_mcp_tool

    proxy = MagicMock()
    proxy.call_tool = AsyncMock(return_value="result")
    getter = MagicMock(return_value=proxy)
    state = MagicMock()
    state.variables = None

    await call_mcp_tool(getter, state, "s", "t", {}, "out")
    assert state.variables["out"] == "result"
