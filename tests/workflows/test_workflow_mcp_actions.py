"""Comprehensive tests for gobby.workflows.mcp_actions module.

Tests the call_mcp_tool function with various scenarios including:
- Successful MCP tool calls
- Error handling (missing parameters, disconnected servers, exceptions)
- Variable storage in workflow state
- Edge cases (None values, empty arguments)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.workflows.mcp_actions import call_mcp_tool


class TestCallMcpToolBasic:
    """Basic functionality tests for call_mcp_tool."""

    @pytest.mark.asyncio
    async def test_successful_tool_call(self):
        """Test a successful MCP tool call returns expected result."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={"data": "result"})

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
            arguments={"key": "value"},
        )

        assert result["result"] == {"data": "result"}
        assert result["stored_as"] is None
        mock_mcp_manager.call_tool.assert_called_once_with(
            "test-server", "test-tool", {"key": "value"}
        )

    @pytest.mark.asyncio
    async def test_successful_tool_call_with_output_as(self):
        """Test tool call stores result in workflow variable when output_as specified."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"api-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={"items": [1, 2, 3]})

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="api-server",
            tool_name="list-items",
            arguments={"filter": "active"},
            output_as="api_result",
        )

        assert result["result"] == {"items": [1, 2, 3]}
        assert result["stored_as"] == "api_result"
        assert mock_state.variables["api_result"] == {"items": [1, 2, 3]}

    @pytest.mark.asyncio
    async def test_tool_call_with_empty_arguments(self):
        """Test tool call with None arguments defaults to empty dict."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={"status": "ok"})

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="no-args-tool",
            arguments=None,
        )

        assert result["result"] == {"status": "ok"}
        mock_mcp_manager.call_tool.assert_called_once_with("test-server", "no-args-tool", {})


class TestCallMcpToolMissingParameters:
    """Tests for missing required parameters."""

    @pytest.mark.asyncio
    async def test_missing_server_name(self):
        """Test error when server_name is None."""
        mock_mcp_manager = AsyncMock()
        mock_state = MagicMock()

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name=None,
            tool_name="test-tool",
        )

        assert result["error"] == "Missing server_name or tool_name"
        mock_mcp_manager.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_tool_name(self):
        """Test error when tool_name is None."""
        mock_mcp_manager = AsyncMock()
        mock_state = MagicMock()

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name=None,
        )

        assert result["error"] == "Missing server_name or tool_name"
        mock_mcp_manager.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_both_server_and_tool_name(self):
        """Test error when both server_name and tool_name are None."""
        mock_mcp_manager = AsyncMock()
        mock_state = MagicMock()

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name=None,
            tool_name=None,
        )

        assert result["error"] == "Missing server_name or tool_name"

    @pytest.mark.asyncio
    async def test_empty_server_name(self):
        """Test error when server_name is empty string."""
        mock_mcp_manager = AsyncMock()
        mock_state = MagicMock()

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="",
            tool_name="test-tool",
        )

        assert result["error"] == "Missing server_name or tool_name"

    @pytest.mark.asyncio
    async def test_empty_tool_name(self):
        """Test error when tool_name is empty string."""
        mock_mcp_manager = AsyncMock()
        mock_state = MagicMock()

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="",
        )

        assert result["error"] == "Missing server_name or tool_name"


class TestCallMcpToolMcpManagerUnavailable:
    """Tests for MCP manager unavailability."""

    @pytest.mark.asyncio
    async def test_mcp_manager_is_none(self):
        """Test error when mcp_manager is None."""
        mock_state = MagicMock()

        result = await call_mcp_tool(
            mcp_manager=None,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
        )

        assert result["error"] == "MCP manager not available"


class TestCallMcpToolServerNotConnected:
    """Tests for server connection issues."""

    @pytest.mark.asyncio
    async def test_server_not_in_connections(self):
        """Test error when server is not connected."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"other-server": MagicMock()}

        mock_state = MagicMock()

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="missing-server",
            tool_name="test-tool",
        )

        assert result["error"] == "Server missing-server not connected"
        mock_mcp_manager.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_connections(self):
        """Test error when connections dict is empty."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {}

        mock_state = MagicMock()

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="any-server",
            tool_name="test-tool",
        )

        assert result["error"] == "Server any-server not connected"


class TestCallMcpToolExceptionHandling:
    """Tests for exception handling during tool execution."""

    @pytest.mark.asyncio
    async def test_call_tool_raises_exception(self):
        """Test error handling when call_tool raises an exception."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(side_effect=Exception("Network timeout"))

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
        )

        assert result["error"] == "Network timeout"

    @pytest.mark.asyncio
    async def test_call_tool_raises_value_error(self):
        """Test error handling when call_tool raises ValueError."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(side_effect=ValueError("Invalid argument format"))

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
            arguments={"bad": "data"},
        )

        assert result["error"] == "Invalid argument format"

    @pytest.mark.asyncio
    async def test_call_tool_raises_runtime_error(self):
        """Test error handling when call_tool raises RuntimeError."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(
            side_effect=RuntimeError("Server disconnected during call")
        )

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
        )

        assert result["error"] == "Server disconnected during call"


class TestCallMcpToolOutputStorage:
    """Tests for workflow variable storage functionality."""

    @pytest.mark.asyncio
    async def test_output_as_creates_variables_dict_when_none(self):
        """Test output_as initializes variables dict if None."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={"value": 42})

        mock_state = MagicMock()
        mock_state.variables = None  # Simulate uninitialized variables

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="get-value",
            output_as="result_var",
        )

        assert result["result"] == {"value": 42}
        assert result["stored_as"] == "result_var"
        assert mock_state.variables is not None
        assert mock_state.variables["result_var"] == {"value": 42}

    @pytest.mark.asyncio
    async def test_output_as_adds_to_existing_variables(self):
        """Test output_as adds to existing variables without overwriting."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={"new": "data"})

        mock_state = MagicMock()
        mock_state.variables = {"existing_var": "old_value"}

        await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
            output_as="new_var",
        )

        assert mock_state.variables["existing_var"] == "old_value"
        assert mock_state.variables["new_var"] == {"new": "data"}

    @pytest.mark.asyncio
    async def test_output_as_overwrites_existing_variable(self):
        """Test output_as overwrites an existing variable with same name."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={"updated": True})

        mock_state = MagicMock()
        mock_state.variables = {"target_var": "initial_value"}

        await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
            output_as="target_var",
        )

        assert mock_state.variables["target_var"] == {"updated": True}

    @pytest.mark.asyncio
    async def test_output_as_with_none_state_raises_error(self):
        """Test output_as raises ValueError when state is None."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={"data": "value"})

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=None,  # State is None but output_as is specified
            server_name="test-server",
            tool_name="test-tool",
            output_as="result_var",
        )

        assert "error" in result
        assert "state must be provided" in result["error"]


class TestCallMcpToolComplexArguments:
    """Tests for complex argument structures."""

    @pytest.mark.asyncio
    async def test_nested_dict_arguments(self):
        """Test tool call with deeply nested dictionary arguments."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={"success": True})

        mock_state = MagicMock()
        mock_state.variables = {}

        complex_args = {
            "level1": {"level2": {"level3": {"value": 123}}},
            "list": [1, 2, {"nested": "item"}],
        }

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="complex-tool",
            arguments=complex_args,
        )

        assert result["result"] == {"success": True}
        mock_mcp_manager.call_tool.assert_called_once_with(
            "test-server", "complex-tool", complex_args
        )

    @pytest.mark.asyncio
    async def test_list_arguments(self):
        """Test tool call with list values in arguments."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={"processed": 5})

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="batch-process",
            arguments={"items": [1, 2, 3, 4, 5], "operation": "sum"},
        )

        assert result["result"] == {"processed": 5}


class TestCallMcpToolReturnValues:
    """Tests for various return value scenarios."""

    @pytest.mark.asyncio
    async def test_returns_none_from_tool(self):
        """Test handling when tool returns None."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value=None)

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="void-tool",
        )

        assert result["result"] is None
        assert result["stored_as"] is None

    @pytest.mark.asyncio
    async def test_returns_empty_dict_from_tool(self):
        """Test handling when tool returns empty dict."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={})

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="empty-result-tool",
        )

        assert result["result"] == {}

    @pytest.mark.asyncio
    async def test_returns_list_from_tool(self):
        """Test handling when tool returns a list."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value=["item1", "item2", "item3"])

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="list-tool",
            output_as="list_result",
        )

        assert result["result"] == ["item1", "item2", "item3"]
        assert mock_state.variables["list_result"] == ["item1", "item2", "item3"]

    @pytest.mark.asyncio
    async def test_returns_string_from_tool(self):
        """Test handling when tool returns a string."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value="string result")

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="string-tool",
        )

        assert result["result"] == "string result"

    @pytest.mark.asyncio
    async def test_returns_integer_from_tool(self):
        """Test handling when tool returns an integer."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value=42)

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="int-tool",
            output_as="number",
        )

        assert result["result"] == 42
        assert mock_state.variables["number"] == 42

    @pytest.mark.asyncio
    async def test_returns_boolean_from_tool(self):
        """Test handling when tool returns a boolean."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value=True)

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="bool-tool",
        )

        assert result["result"] is True


class TestCallMcpToolEdgeCases:
    """Edge case tests for call_mcp_tool."""

    @pytest.mark.asyncio
    async def test_server_name_with_special_characters(self):
        """Test server name with hyphens and underscores."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"my-test_server-v2": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={"ok": True})

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="my-test_server-v2",
            tool_name="test-tool",
        )

        assert result["result"] == {"ok": True}

    @pytest.mark.asyncio
    async def test_tool_name_with_special_characters(self):
        """Test tool name with hyphens, underscores, and dots."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={"ok": True})

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="my_tool.v2-beta",
        )

        assert result["result"] == {"ok": True}
        mock_mcp_manager.call_tool.assert_called_once_with("test-server", "my_tool.v2-beta", {})

    @pytest.mark.asyncio
    async def test_output_as_with_special_characters(self):
        """Test output_as variable name with underscores."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={"data": 123})

        mock_state = MagicMock()
        mock_state.variables = {}

        await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
            output_as="my_result_var_2",
        )

        assert mock_state.variables["my_result_var_2"] == {"data": 123}

    @pytest.mark.asyncio
    async def test_arguments_with_none_values(self):
        """Test arguments dict containing None values."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={"processed": True})

        mock_state = MagicMock()
        mock_state.variables = {}

        args_with_none = {
            "required_param": "value",
            "optional_param": None,
            "another_optional": None,
        }

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
            arguments=args_with_none,
        )

        assert result["result"] == {"processed": True}
        mock_mcp_manager.call_tool.assert_called_once_with(
            "test-server", "test-tool", args_with_none
        )

    @pytest.mark.asyncio
    async def test_arguments_with_empty_string_values(self):
        """Test arguments dict containing empty string values."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={"valid": True})

        mock_state = MagicMock()
        mock_state.variables = {}

        args_with_empty_strings = {
            "param1": "value",
            "param2": "",
            "param3": "",
        }

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
            arguments=args_with_empty_strings,
        )

        assert result["result"] == {"valid": True}

    @pytest.mark.asyncio
    async def test_large_result_stored_in_variable(self):
        """Test storing a large result in workflow variable."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}

        # Simulate a large result
        large_result = {"items": [{"id": i, "data": "x" * 1000} for i in range(100)]}
        mock_mcp_manager.call_tool = AsyncMock(return_value=large_result)

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="bulk-fetch",
            output_as="bulk_data",
        )

        assert result["result"] == large_result
        assert mock_state.variables["bulk_data"] == large_result
        assert len(mock_state.variables["bulk_data"]["items"]) == 100


class TestCallMcpToolWithRealWorkflowState:
    """Tests using actual WorkflowState objects."""

    @pytest.mark.asyncio
    async def test_with_workflow_state_dataclass(self):
        """Test with an actual WorkflowState-like object."""
        from dataclasses import dataclass, field

        @dataclass
        class MockWorkflowState:
            session_id: str
            workflow_name: str
            step: str
            variables: dict = field(default_factory=dict)

        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.call_tool = AsyncMock(return_value={"status": "complete"})

        state = MockWorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="execute",
            variables={"existing": "value"},
        )

        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=state,
            server_name="test-server",
            tool_name="test-tool",
            output_as="new_result",
        )

        assert result["result"] == {"status": "complete"}
        assert state.variables["existing"] == "value"
        assert state.variables["new_result"] == {"status": "complete"}


class TestCallMcpToolMultipleCalls:
    """Tests for multiple sequential tool calls."""

    @pytest.mark.asyncio
    async def test_multiple_calls_accumulate_in_variables(self):
        """Test that multiple calls accumulate results in variables."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {
            "server1": MagicMock(),
            "server2": MagicMock(),
        }

        mock_state = MagicMock()
        mock_state.variables = {}

        # First call
        mock_mcp_manager.call_tool = AsyncMock(return_value={"data": "first"})
        await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="server1",
            tool_name="tool1",
            output_as="result1",
        )

        # Second call
        mock_mcp_manager.call_tool = AsyncMock(return_value={"data": "second"})
        await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="server2",
            tool_name="tool2",
            output_as="result2",
        )

        # Both results should be stored
        assert mock_state.variables["result1"] == {"data": "first"}
        assert mock_state.variables["result2"] == {"data": "second"}

    @pytest.mark.asyncio
    async def test_error_does_not_affect_previous_variables(self):
        """Test that an error in a call doesn't affect previously stored variables."""
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.connections = {"test-server": MagicMock()}

        mock_state = MagicMock()
        mock_state.variables = {}

        # Successful first call
        mock_mcp_manager.call_tool = AsyncMock(return_value={"success": True})
        await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="tool1",
            output_as="good_result",
        )

        # Second call fails
        mock_mcp_manager.call_tool = AsyncMock(side_effect=Exception("Failed"))
        result = await call_mcp_tool(
            mcp_manager=mock_mcp_manager,
            state=mock_state,
            server_name="test-server",
            tool_name="tool2",
            output_as="bad_result",
        )

        # First result should still be there
        assert mock_state.variables["good_result"] == {"success": True}
        # Error result should not add to variables
        assert "bad_result" not in mock_state.variables
        assert "error" in result
