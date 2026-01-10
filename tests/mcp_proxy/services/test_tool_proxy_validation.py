"""Tests for call_tool pre-validation of arguments.

These tests verify that the ToolProxyService:
1. Returns helpful error with schema when wrong parameter names are used
2. Returns helpful error with schema when required parameters are missing
3. Error response includes full tool schema for reference
4. Valid parameters pass through normally
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.mcp_proxy.services.tool_proxy import ToolProxyService


@pytest.fixture
def mock_mcp_manager():
    """Create a mock MCP manager."""
    manager = MagicMock()
    manager.project_id = "test-project-id"
    manager.call_tool = AsyncMock()
    manager.get_tool_schema = AsyncMock()
    return manager


@pytest.fixture
def mock_internal_manager():
    """Create a mock internal registry manager."""
    manager = MagicMock()
    manager.is_internal.return_value = False
    return manager


@pytest.fixture
def tool_proxy(mock_mcp_manager, mock_internal_manager):
    """Create ToolProxyService with validation enabled."""
    return ToolProxyService(
        mcp_manager=mock_mcp_manager,
        internal_manager=mock_internal_manager,
        validate_arguments=True,
    )


@pytest.fixture
def tool_proxy_no_validation(mock_mcp_manager, mock_internal_manager):
    """Create ToolProxyService with validation disabled."""
    return ToolProxyService(
        mcp_manager=mock_mcp_manager,
        internal_manager=mock_internal_manager,
        validate_arguments=False,
    )


class TestCheckArguments:
    """Tests for the _check_arguments validation method."""

    def test_valid_arguments_returns_empty_list(self, tool_proxy):
        """Verify valid arguments return no errors."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["name"],
        }
        arguments = {"name": "test", "count": 5}

        errors = tool_proxy._check_arguments(arguments, schema)

        assert errors == []

    def test_unknown_parameter_returns_error(self, tool_proxy):
        """Verify unknown parameter names are flagged."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": [],
        }
        arguments = {"workflow_name": "test"}  # Wrong: should be "name"

        errors = tool_proxy._check_arguments(arguments, schema)

        assert len(errors) == 1
        assert "Unknown parameter 'workflow_name'" in errors[0]
        assert "name" in errors[0]  # Should suggest similar param

    def test_unknown_parameter_lists_valid_parameters(self, tool_proxy):
        """Verify error lists valid parameters when no similar match."""
        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": [],
        }
        arguments = {"xyz": "test"}  # No similar match

        errors = tool_proxy._check_arguments(arguments, schema)

        assert len(errors) == 1
        assert "Unknown parameter 'xyz'" in errors[0]
        assert "Valid parameters:" in errors[0]
        assert "title" in errors[0]

    def test_missing_required_parameter_returns_error(self, tool_proxy):
        """Verify missing required parameters are flagged."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["name", "session_id"],
        }
        arguments = {"name": "test"}  # Missing session_id

        errors = tool_proxy._check_arguments(arguments, schema)

        assert len(errors) == 1
        assert "Missing required parameter 'session_id'" in errors[0]

    def test_multiple_errors_returned(self, tool_proxy):
        """Verify multiple errors are returned together."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["name", "session_id"],
        }
        arguments = {"wrong_param": "test"}  # Missing both + unknown param

        errors = tool_proxy._check_arguments(arguments, schema)

        assert len(errors) == 3  # 1 unknown + 2 missing
        error_text = " ".join(errors)
        assert "Unknown parameter 'wrong_param'" in error_text
        assert "Missing required parameter 'name'" in error_text
        assert "Missing required parameter 'session_id'" in error_text

    def test_empty_arguments_with_no_required(self, tool_proxy):
        """Verify empty arguments pass if nothing is required."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": [],
        }
        arguments = {}

        errors = tool_proxy._check_arguments(arguments, schema)

        assert errors == []

    def test_empty_schema_accepts_all(self, tool_proxy):
        """Verify empty schema accepts any arguments (no validation possible)."""
        schema = {}
        arguments = {"anything": "goes"}

        errors = tool_proxy._check_arguments(arguments, schema)

        # With no properties defined, we can't validate - but currently
        # the code would flag "anything" as unknown. This tests current behavior.
        # If empty properties means "accept all", this test should be updated.
        assert len(errors) == 1
        assert "Unknown parameter 'anything'" in errors[0]


class TestCallToolPreValidation:
    """Tests for call_tool pre-validation behavior."""

    @pytest.mark.asyncio
    async def test_returns_error_with_schema_for_invalid_args(
        self, tool_proxy, mock_mcp_manager
    ):
        """Verify invalid arguments return error with schema included."""
        # Setup mock to return tool schema
        tool_proxy._mcp_manager = mock_mcp_manager
        mock_mcp_manager.get_tool_schema = AsyncMock(
            return_value={
                "name": "test_tool",
                "description": "A test tool",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The name"},
                        "session_id": {"type": "string"},
                    },
                    "required": ["name"],
                },
            }
        )

        # Mock get_tool_schema on the service
        async def mock_get_schema(server, tool):
            return {
                "success": True,
                "tool": {
                    "name": tool,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "session_id": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                },
            }

        tool_proxy.get_tool_schema = mock_get_schema

        # Call with wrong parameter name
        result = await tool_proxy.call_tool(
            server_name="test-server",
            tool_name="test_tool",
            arguments={"workflow_name": "test"},  # Wrong param name
        )

        assert result["success"] is False
        assert "Invalid arguments" in result["error"]
        assert "workflow_name" in result["error"]
        assert "schema" in result
        assert "hint" in result
        assert result["server_name"] == "test-server"
        assert result["tool_name"] == "test_tool"

    @pytest.mark.asyncio
    async def test_returns_error_with_schema_for_missing_required(
        self, tool_proxy, mock_mcp_manager
    ):
        """Verify missing required parameters return error with schema."""
        async def mock_get_schema(server, tool):
            return {
                "success": True,
                "tool": {
                    "name": tool,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "session_id": {"type": "string"},
                        },
                        "required": ["name", "session_id"],
                    },
                },
            }

        tool_proxy.get_tool_schema = mock_get_schema

        # Call with missing required parameter
        result = await tool_proxy.call_tool(
            server_name="test-server",
            tool_name="test_tool",
            arguments={"name": "test"},  # Missing session_id
        )

        assert result["success"] is False
        assert "Invalid arguments" in result["error"]
        assert "session_id" in result["error"]
        assert "schema" in result

    @pytest.mark.asyncio
    async def test_valid_arguments_pass_through(
        self, tool_proxy, mock_mcp_manager
    ):
        """Verify valid arguments pass through to execution."""
        async def mock_get_schema(server, tool):
            return {
                "success": True,
                "tool": {
                    "name": tool,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                },
            }

        tool_proxy.get_tool_schema = mock_get_schema
        mock_mcp_manager.call_tool.return_value = {"success": True, "result": "done"}

        result = await tool_proxy.call_tool(
            server_name="test-server",
            tool_name="test_tool",
            arguments={"name": "test"},
        )

        assert result["success"] is True
        mock_mcp_manager.call_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_validation_when_disabled(
        self, tool_proxy_no_validation, mock_mcp_manager
    ):
        """Verify no validation when validate_arguments is False."""
        mock_mcp_manager.call_tool.return_value = {"success": True}

        result = await tool_proxy_no_validation.call_tool(
            server_name="test-server",
            tool_name="test_tool",
            arguments={"wrong_param": "test"},  # Would fail validation
        )

        # Should pass through without validation
        mock_mcp_manager.call_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_validation_for_empty_arguments(
        self, tool_proxy, mock_mcp_manager
    ):
        """Verify no validation is performed when arguments are empty."""
        mock_mcp_manager.call_tool.return_value = {"success": True}

        result = await tool_proxy.call_tool(
            server_name="test-server",
            tool_name="test_tool",
            arguments={},  # Empty args
        )

        # Should pass through - empty args don't trigger validation
        mock_mcp_manager.call_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_schema_fetch_failure_allows_execution(
        self, tool_proxy, mock_mcp_manager
    ):
        """Verify tool execution proceeds when schema fetch fails."""
        async def mock_get_schema(server, tool):
            return {"success": False, "error": "Schema not found"}

        tool_proxy.get_tool_schema = mock_get_schema
        mock_mcp_manager.call_tool.return_value = {"success": True}

        result = await tool_proxy.call_tool(
            server_name="test-server",
            tool_name="test_tool",
            arguments={"some_param": "test"},
        )

        # Should still attempt execution when schema is unavailable
        mock_mcp_manager.call_tool.assert_called_once()


class TestCallToolInternalServer:
    """Tests for call_tool with internal servers (gobby-*)."""

    @pytest.mark.asyncio
    async def test_validates_internal_tool_arguments(
        self, tool_proxy, mock_internal_manager
    ):
        """Verify internal tool arguments are validated."""
        # Setup internal server detection
        mock_internal_manager.is_internal.return_value = True
        mock_registry = MagicMock()
        mock_registry.call = AsyncMock(return_value={"success": True})
        mock_internal_manager.get_registry.return_value = mock_registry

        # Setup schema
        async def mock_get_schema(server, tool):
            return {
                "success": True,
                "tool": {
                    "name": tool,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "string"},
                        },
                        "required": ["task_id"],
                    },
                },
            }

        tool_proxy.get_tool_schema = mock_get_schema

        # Call with wrong parameter name
        result = await tool_proxy.call_tool(
            server_name="gobby-tasks",
            tool_name="get_task",
            arguments={"id": "gt-123"},  # Wrong: should be task_id
        )

        assert result["success"] is False
        assert "Unknown parameter 'id'" in result["error"]
        assert "task_id" in result["error"]  # Should suggest correct param

    @pytest.mark.asyncio
    async def test_valid_internal_tool_execution(
        self, tool_proxy, mock_internal_manager
    ):
        """Verify valid internal tool calls execute successfully."""
        mock_internal_manager.is_internal.return_value = True
        mock_registry = MagicMock()
        mock_registry.call = AsyncMock(return_value={"id": "gt-123", "title": "Test"})
        mock_internal_manager.get_registry.return_value = mock_registry

        async def mock_get_schema(server, tool):
            return {
                "success": True,
                "tool": {
                    "name": tool,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "string"},
                        },
                        "required": ["task_id"],
                    },
                },
            }

        tool_proxy.get_tool_schema = mock_get_schema

        result = await tool_proxy.call_tool(
            server_name="gobby-tasks",
            tool_name="get_task",
            arguments={"task_id": "gt-123"},
        )

        assert result["id"] == "gt-123"
        mock_registry.call.assert_called_once_with("get_task", {"task_id": "gt-123"})
