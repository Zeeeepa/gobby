"""Comprehensive tests for gobby.workflows.mcp_actions module.

Tests the call_mcp_tool function with various scenarios including:
- Successful MCP tool calls via ToolProxyService
- Error handling (missing parameters, unavailable proxy, exceptions)
- Variable storage in workflow state
- Edge cases (None values, empty arguments)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.workflows.mcp_actions import call_mcp_tool

pytestmark = pytest.mark.unit


def _make_proxy(return_value: object = None, side_effect: Exception | None = None) -> AsyncMock:
    """Create a mock tool proxy with call_tool configured."""
    proxy = AsyncMock()
    proxy.call_tool = AsyncMock(return_value=return_value, side_effect=side_effect)
    return proxy


class TestCallMcpToolBasic:
    """Basic functionality tests for call_mcp_tool."""

    @pytest.mark.asyncio
    async def test_successful_tool_call(self):
        """Test a successful MCP tool call returns expected result."""
        mock_proxy = _make_proxy(return_value={"data": "result"})

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
            arguments={"key": "value"},
        )

        assert result["result"] == {"data": "result"}
        assert result["stored_as"] is None
        mock_proxy.call_tool.assert_called_once_with(
            "test-server", "test-tool", {"key": "value"}
        )

    @pytest.mark.asyncio
    async def test_successful_tool_call_with_output_as(self):
        """Test tool call stores result in workflow variable when output_as specified."""
        mock_proxy = _make_proxy(return_value={"items": [1, 2, 3]})

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
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
        mock_proxy = _make_proxy(return_value={"status": "ok"})

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="test-server",
            tool_name="no-args-tool",
            arguments=None,
        )

        assert result["result"] == {"status": "ok"}
        mock_proxy.call_tool.assert_called_once_with("test-server", "no-args-tool", {})


class TestCallMcpToolMissingParameters:
    """Tests for missing required parameters."""

    @pytest.mark.asyncio
    async def test_missing_server_name(self):
        """Test error when server_name is None."""
        mock_proxy = _make_proxy()
        mock_state = MagicMock()

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name=None,
            tool_name="test-tool",
        )

        assert result["error"] == "Missing server_name or tool_name"
        mock_proxy.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_tool_name(self):
        """Test error when tool_name is None."""
        mock_proxy = _make_proxy()
        mock_state = MagicMock()

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="test-server",
            tool_name=None,
        )

        assert result["error"] == "Missing server_name or tool_name"
        mock_proxy.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_both_server_and_tool_name(self):
        """Test error when both server_name and tool_name are None."""
        mock_proxy = _make_proxy()
        mock_state = MagicMock()

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name=None,
            tool_name=None,
        )

        assert result["error"] == "Missing server_name or tool_name"

    @pytest.mark.asyncio
    async def test_empty_server_name(self):
        """Test error when server_name is empty string."""
        mock_proxy = _make_proxy()
        mock_state = MagicMock()

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="",
            tool_name="test-tool",
        )

        assert result["error"] == "Missing server_name or tool_name"

    @pytest.mark.asyncio
    async def test_empty_tool_name(self):
        """Test error when tool_name is empty string."""
        mock_proxy = _make_proxy()
        mock_state = MagicMock()

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="test-server",
            tool_name="",
        )

        assert result["error"] == "Missing server_name or tool_name"


class TestCallMcpToolProxyUnavailable:
    """Tests for tool proxy unavailability."""

    @pytest.mark.asyncio
    async def test_tool_proxy_getter_is_none(self):
        """Test error when tool_proxy_getter is None."""
        mock_state = MagicMock()

        result = await call_mcp_tool(
            tool_proxy_getter=None,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
        )

        assert result["error"] == "Tool proxy not available"

    @pytest.mark.asyncio
    async def test_tool_proxy_getter_returns_none(self):
        """Test error when tool_proxy_getter callable returns None."""
        mock_state = MagicMock()

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: None,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
        )

        assert result["error"] == "Tool proxy not available"


class TestCallMcpToolExceptionHandling:
    """Tests for exception handling during tool execution."""

    @pytest.mark.asyncio
    async def test_call_tool_raises_exception(self):
        """Test error handling when call_tool raises an exception."""
        mock_proxy = _make_proxy(side_effect=Exception("Network timeout"))

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
        )

        assert result["error"] == "Network timeout"

    @pytest.mark.asyncio
    async def test_call_tool_raises_value_error(self):
        """Test error handling when call_tool raises ValueError."""
        mock_proxy = _make_proxy(side_effect=ValueError("Invalid argument format"))

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
            arguments={"bad": "data"},
        )

        assert result["error"] == "Invalid argument format"

    @pytest.mark.asyncio
    async def test_call_tool_raises_runtime_error(self):
        """Test error handling when call_tool raises RuntimeError."""
        mock_proxy = _make_proxy(side_effect=RuntimeError("Server disconnected during call"))

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
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
        mock_proxy = _make_proxy(return_value={"value": 42})

        mock_state = MagicMock()
        mock_state.variables = None  # Simulate uninitialized variables

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
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
        mock_proxy = _make_proxy(return_value={"new": "data"})

        mock_state = MagicMock()
        mock_state.variables = {"existing_var": "old_value"}

        await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
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
        mock_proxy = _make_proxy(return_value={"updated": True})

        mock_state = MagicMock()
        mock_state.variables = {"target_var": "initial_value"}

        await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
            output_as="target_var",
        )

        assert mock_state.variables["target_var"] == {"updated": True}

    @pytest.mark.asyncio
    async def test_output_as_with_none_state_raises_error(self):
        """Test output_as raises ValueError when state is None."""
        mock_proxy = _make_proxy(return_value={"data": "value"})

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
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
        mock_proxy = _make_proxy(return_value={"success": True})

        mock_state = MagicMock()
        mock_state.variables = {}

        complex_args = {
            "level1": {"level2": {"level3": {"value": 123}}},
            "list": [1, 2, {"nested": "item"}],
        }

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="test-server",
            tool_name="complex-tool",
            arguments=complex_args,
        )

        assert result["result"] == {"success": True}
        mock_proxy.call_tool.assert_called_once_with(
            "test-server", "complex-tool", complex_args
        )

    @pytest.mark.asyncio
    async def test_list_arguments(self):
        """Test tool call with list values in arguments."""
        mock_proxy = _make_proxy(return_value={"processed": 5})

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
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
        mock_proxy = _make_proxy(return_value=None)

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="test-server",
            tool_name="void-tool",
        )

        assert result["result"] is None
        assert result["stored_as"] is None

    @pytest.mark.asyncio
    async def test_returns_empty_dict_from_tool(self):
        """Test handling when tool returns empty dict."""
        mock_proxy = _make_proxy(return_value={})

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="test-server",
            tool_name="empty-result-tool",
        )

        assert result["result"] == {}

    @pytest.mark.asyncio
    async def test_returns_list_from_tool(self):
        """Test handling when tool returns a list."""
        mock_proxy = _make_proxy(return_value=["item1", "item2", "item3"])

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
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
        mock_proxy = _make_proxy(return_value="string result")

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="test-server",
            tool_name="string-tool",
        )

        assert result["result"] == "string result"

    @pytest.mark.asyncio
    async def test_returns_integer_from_tool(self):
        """Test handling when tool returns an integer."""
        mock_proxy = _make_proxy(return_value=42)

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
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
        mock_proxy = _make_proxy(return_value=True)

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
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
        mock_proxy = _make_proxy(return_value={"ok": True})

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="my-test_server-v2",
            tool_name="test-tool",
        )

        assert result["result"] == {"ok": True}

    @pytest.mark.asyncio
    async def test_tool_name_with_special_characters(self):
        """Test tool name with hyphens, underscores, and dots."""
        mock_proxy = _make_proxy(return_value={"ok": True})

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="test-server",
            tool_name="my_tool.v2-beta",
        )

        assert result["result"] == {"ok": True}
        mock_proxy.call_tool.assert_called_once_with("test-server", "my_tool.v2-beta", {})

    @pytest.mark.asyncio
    async def test_output_as_with_special_characters(self):
        """Test output_as variable name with underscores."""
        mock_proxy = _make_proxy(return_value={"data": 123})

        mock_state = MagicMock()
        mock_state.variables = {}

        await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
            output_as="my_result_var_2",
        )

        assert mock_state.variables["my_result_var_2"] == {"data": 123}

    @pytest.mark.asyncio
    async def test_arguments_with_none_values(self):
        """Test arguments dict containing None values."""
        mock_proxy = _make_proxy(return_value={"processed": True})

        mock_state = MagicMock()
        mock_state.variables = {}

        args_with_none = {
            "required_param": "value",
            "optional_param": None,
            "another_optional": None,
        }

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
            arguments=args_with_none,
        )

        assert result["result"] == {"processed": True}
        mock_proxy.call_tool.assert_called_once_with(
            "test-server", "test-tool", args_with_none
        )

    @pytest.mark.asyncio
    async def test_arguments_with_empty_string_values(self):
        """Test arguments dict containing empty string values."""
        mock_proxy = _make_proxy(return_value={"valid": True})

        mock_state = MagicMock()
        mock_state.variables = {}

        args_with_empty_strings = {
            "param1": "value",
            "param2": "",
            "param3": "",
        }

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
            state=mock_state,
            server_name="test-server",
            tool_name="test-tool",
            arguments=args_with_empty_strings,
        )

        assert result["result"] == {"valid": True}

    @pytest.mark.asyncio
    async def test_large_result_stored_in_variable(self):
        """Test storing a large result in workflow variable."""
        # Simulate a large result
        large_result = {"items": [{"id": i, "data": "x" * 1000} for i in range(100)]}
        mock_proxy = _make_proxy(return_value=large_result)

        mock_state = MagicMock()
        mock_state.variables = {}

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
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

        mock_proxy = _make_proxy(return_value={"status": "complete"})

        state = MockWorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="execute",
            variables={"existing": "value"},
        )

        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy,
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
        mock_state = MagicMock()
        mock_state.variables = {}

        # First call
        mock_proxy1 = _make_proxy(return_value={"data": "first"})
        await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy1,
            state=mock_state,
            server_name="server1",
            tool_name="tool1",
            output_as="result1",
        )

        # Second call
        mock_proxy2 = _make_proxy(return_value={"data": "second"})
        await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy2,
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
        mock_state = MagicMock()
        mock_state.variables = {}

        # Successful first call
        mock_proxy1 = _make_proxy(return_value={"success": True})
        await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy1,
            state=mock_state,
            server_name="test-server",
            tool_name="tool1",
            output_as="good_result",
        )

        # Second call fails
        mock_proxy2 = _make_proxy(side_effect=Exception("Failed"))
        result = await call_mcp_tool(
            tool_proxy_getter=lambda: mock_proxy2,
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


# =============================================================================
# Tests for _render_arguments
# =============================================================================


class TestRenderArguments:
    """Tests for _render_arguments template rendering helper."""

    def test_renders_simple_template(self):
        """String values with {{ }} are rendered via template engine."""
        from gobby.workflows.mcp_actions import _render_arguments
        from gobby.workflows.templates import TemplateEngine

        engine = TemplateEngine()
        context = {"variables": {"task_id": "abc-123"}}

        result = _render_arguments(
            {"task_id": "{{ variables.task_id }}", "static": "value"},
            engine,
            context,
        )

        assert result["task_id"] == "abc-123"
        assert result["static"] == "value"

    def test_renders_nested_dict(self):
        """Nested dict values are recursively rendered."""
        from gobby.workflows.mcp_actions import _render_arguments
        from gobby.workflows.templates import TemplateEngine

        engine = TemplateEngine()
        context = {"variables": {"name": "test"}}

        result = _render_arguments(
            {"outer": {"inner": "{{ variables.name }}"}},
            engine,
            context,
        )

        assert result["outer"]["inner"] == "test"

    def test_renders_list_values(self):
        """List items with templates are rendered."""
        from gobby.workflows.mcp_actions import _render_arguments
        from gobby.workflows.templates import TemplateEngine

        engine = TemplateEngine()
        context = {"variables": {"x": "hello"}}

        result = _render_arguments(
            {"items": ["{{ variables.x }}", "static", 42]},
            engine,
            context,
        )

        assert result["items"] == ["hello", "static", 42]

    def test_leaves_non_template_strings(self):
        """Strings without {{ }} are not modified."""
        from gobby.workflows.mcp_actions import _render_arguments
        from gobby.workflows.templates import TemplateEngine

        engine = TemplateEngine()
        context = {}

        result = _render_arguments(
            {"key": "plain string", "num": 42, "flag": True},
            engine,
            context,
        )

        assert result == {"key": "plain string", "num": 42, "flag": True}


# =============================================================================
# Tests for handle_call_mcp_tool template rendering and inject_message
# =============================================================================


class TestHandleCallMcpToolTemplateRendering:
    """Tests for template rendering and inject_message in handle_call_mcp_tool."""

    @pytest.mark.asyncio
    async def test_renders_templates_in_arguments(self):
        """Arguments containing {{ }} templates are rendered before calling."""
        from gobby.workflows.actions import ActionContext
        from gobby.workflows.definitions import WorkflowState
        from gobby.workflows.templates import TemplateEngine

        mock_proxy = _make_proxy(return_value={"suggestion": {"ref": "#42"}})

        state = WorkflowState(
            session_id="sess-1",
            workflow_name="test",
            step="find_work",
            variables={"my_var": "resolved_value"},
        )

        ctx = ActionContext(
            session_id="sess-1",
            state=state,
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=TemplateEngine(),
            tool_proxy_getter=lambda: mock_proxy,
        )

        from gobby.workflows.mcp_actions import handle_call_mcp_tool

        result = await handle_call_mcp_tool(
            ctx,
            server_name="gobby-tasks",
            tool_name="suggest_next_task",
            arguments={"session_id": "{{ session_id }}", "extra": "{{ variables.my_var }}"},
        )

        # Arguments should have been rendered
        mock_proxy.call_tool.assert_called_once_with(
            "gobby-tasks",
            "suggest_next_task",
            {"session_id": "sess-1", "extra": "resolved_value"},
        )
        assert "error" not in result
        assert "inject_message" in result

    @pytest.mark.asyncio
    async def test_output_as_alias(self):
        """Both 'as' and 'output_as' kwargs are supported."""
        from gobby.workflows.actions import ActionContext
        from gobby.workflows.definitions import WorkflowState
        from gobby.workflows.templates import TemplateEngine

        mock_proxy = _make_proxy(return_value={"data": "ok"})

        state = WorkflowState(
            session_id="sess-1",
            workflow_name="test",
            step="step1",
            variables={},
        )

        ctx = ActionContext(
            session_id="sess-1",
            state=state,
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=TemplateEngine(),
            tool_proxy_getter=lambda: mock_proxy,
        )

        from gobby.workflows.mcp_actions import handle_call_mcp_tool

        result = await handle_call_mcp_tool(
            ctx,
            server_name="test-server",
            tool_name="test-tool",
            output_as="_my_result",
        )

        assert result["stored_as"] == "_my_result"
        assert state.variables["_my_result"] == {"data": "ok"}

    @pytest.mark.asyncio
    async def test_returns_inject_message_on_success(self):
        """Successful calls include inject_message for LLM context."""
        from gobby.workflows.actions import ActionContext
        from gobby.workflows.definitions import WorkflowState
        from gobby.workflows.templates import TemplateEngine

        mock_proxy = _make_proxy(return_value={})

        state = WorkflowState(
            session_id="sess-1",
            workflow_name="test",
            step="step1",
            variables={},
        )

        ctx = ActionContext(
            session_id="sess-1",
            state=state,
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=TemplateEngine(),
            tool_proxy_getter=lambda: mock_proxy,
        )

        from gobby.workflows.mcp_actions import handle_call_mcp_tool

        result = await handle_call_mcp_tool(
            ctx,
            server_name="srv",
            tool_name="my_tool",
        )

        assert "inject_message" in result
        assert "srv/my_tool" in result["inject_message"]

    @pytest.mark.asyncio
    async def test_no_inject_message_on_error(self):
        """Error results do NOT include inject_message."""
        from gobby.workflows.actions import ActionContext
        from gobby.workflows.definitions import WorkflowState
        from gobby.workflows.templates import TemplateEngine

        state = WorkflowState(
            session_id="sess-1",
            workflow_name="test",
            step="step1",
            variables={},
        )

        ctx = ActionContext(
            session_id="sess-1",
            state=state,
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=TemplateEngine(),
            tool_proxy_getter=None,  # Will cause "Tool proxy not available" error
        )

        from gobby.workflows.mcp_actions import handle_call_mcp_tool

        result = await handle_call_mcp_tool(
            ctx,
            server_name="srv",
            tool_name="my_tool",
        )

        assert "error" in result
        assert "inject_message" not in result
