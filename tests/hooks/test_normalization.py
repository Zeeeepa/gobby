"""Tests for shared MCP field normalization."""

import pytest

from gobby.hooks.normalization import normalize_mcp_fields

pytestmark = pytest.mark.unit


class TestMcpPrefixParsing:
    """Tests for mcp__<server>__<tool> prefix parsing (Step 1a)."""

    def test_parses_standard_mcp_prefix(self) -> None:
        data = {"tool_name": "mcp__gobby-tasks__create_task"}
        result = normalize_mcp_fields(data)
        assert result["mcp_server"] == "gobby-tasks"
        assert result["mcp_tool"] == "create_task"

    def test_does_not_overwrite_existing_mcp_tool(self) -> None:
        data = {
            "tool_name": "mcp__gobby__call_tool",
            "mcp_tool": "already_set",
        }
        result = normalize_mcp_fields(data)
        # mcp_tool was already present, so prefix parsing should not overwrite
        assert result["mcp_tool"] == "already_set"

    def test_non_mcp_tool_unchanged(self) -> None:
        data = {"tool_name": "Read", "tool_input": {"file": "foo.py"}}
        result = normalize_mcp_fields(data)
        assert "mcp_server" not in result
        assert "mcp_tool" not in result

    def test_empty_tool_name(self) -> None:
        data = {"tool_name": ""}
        result = normalize_mcp_fields(data)
        assert "mcp_server" not in result
        assert "mcp_tool" not in result

    def test_malformed_prefix_only_two_parts(self) -> None:
        data = {"tool_name": "mcp__incomplete"}
        result = normalize_mcp_fields(data)
        # Only 2 parts after split, no mcp_server/mcp_tool set
        assert "mcp_server" not in result
        assert "mcp_tool" not in result


class TestCallToolExtraction:
    """Tests for call_tool / mcp__gobby__call_tool inner extraction (Step 1b)."""

    def test_mcp_gobby_call_tool_overrides_prefix(self) -> None:
        data = {
            "tool_name": "mcp__gobby__call_tool",
            "tool_input": {"server_name": "gobby-memory", "tool_name": "add_memory"},
        }
        result = normalize_mcp_fields(data)
        # Inner values override prefix-parsed "gobby" / "call_tool"
        assert result["mcp_server"] == "gobby-memory"
        assert result["mcp_tool"] == "add_memory"

    def test_plain_call_tool_sets_from_input(self) -> None:
        data = {
            "tool_name": "call_tool",
            "tool_input": {"server_name": "gobby-tasks", "tool_name": "list_tasks"},
        }
        result = normalize_mcp_fields(data)
        assert result["mcp_server"] == "gobby-tasks"
        assert result["mcp_tool"] == "list_tasks"

    def test_plain_call_tool_preserves_existing(self) -> None:
        data = {
            "tool_name": "call_tool",
            "tool_input": {"server_name": "inner-server", "tool_name": "inner-tool"},
            "mcp_server": "external-server",
            "mcp_tool": "external-tool",
        }
        result = normalize_mcp_fields(data)
        # Plain call_tool should NOT overwrite externally-set values
        assert result["mcp_server"] == "external-server"
        assert result["mcp_tool"] == "external-tool"

    def test_call_tool_missing_inner_fields(self) -> None:
        data = {
            "tool_name": "call_tool",
            "tool_input": {},
        }
        result = normalize_mcp_fields(data)
        assert "mcp_server" not in result
        assert "mcp_tool" not in result

    def test_call_tool_none_tool_input(self) -> None:
        data = {
            "tool_name": "call_tool",
            "tool_input": None,
        }
        result = normalize_mcp_fields(data)
        assert "mcp_server" not in result


class TestToolOutputNormalization:
    """Tests for tool_result / tool_response → tool_output (Step 2)."""

    def test_normalizes_tool_result(self) -> None:
        data = {"tool_result": "success"}
        result = normalize_mcp_fields(data)
        assert result["tool_output"] == "success"

    def test_normalizes_tool_response(self) -> None:
        data = {"tool_response": {"status": "ok"}}
        result = normalize_mcp_fields(data)
        assert result["tool_output"] == {"status": "ok"}

    def test_tool_result_takes_precedence_over_tool_response(self) -> None:
        data = {"tool_result": "from_result", "tool_response": "from_response"}
        result = normalize_mcp_fields(data)
        # tool_result is checked first, so it wins
        assert result["tool_output"] == "from_result"

    def test_existing_tool_output_not_overwritten(self) -> None:
        data = {"tool_result": "from_result", "tool_output": "already_set"}
        result = normalize_mcp_fields(data)
        assert result["tool_output"] == "already_set"

    def test_no_tool_result_or_response(self) -> None:
        data = {"tool_name": "Read"}
        result = normalize_mcp_fields(data)
        assert "tool_output" not in result


class TestCombinedNormalization:
    """Tests verifying all normalizations work together."""

    def test_full_mcp_call_with_result(self) -> None:
        data = {
            "tool_name": "mcp__gobby__call_tool",
            "tool_input": {
                "server_name": "gobby-tasks",
                "tool_name": "create_task",
                "arguments": {"title": "Test"},
            },
            "tool_response": {"id": "task-123"},
        }
        result = normalize_mcp_fields(data)
        assert result["mcp_server"] == "gobby-tasks"
        assert result["mcp_tool"] == "create_task"
        assert result["tool_output"] == {"id": "task-123"}

    def test_mutates_in_place(self) -> None:
        data = {"tool_name": "mcp__s__t"}
        returned = normalize_mcp_fields(data)
        assert returned is data
        assert data["mcp_server"] == "s"
