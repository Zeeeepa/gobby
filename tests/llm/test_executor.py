"""Tests for base executor types and utilities."""

import pytest

from gobby.llm.executor import (
    AgentExecutor,
    AgentResult,
    ToolCallRecord,
    ToolHandler,
    ToolResult,
    ToolSchema,
)

pytestmark = pytest.mark.unit

class TestToolSchema:
    """Tests for ToolSchema dataclass."""

    def test_create_with_required_fields(self) -> None:
        """ToolSchema can be created with required fields."""
        schema = ToolSchema(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
        )

        assert schema.name == "test_tool"
        assert schema.description == "A test tool"
        assert schema.input_schema == {"type": "object", "properties": {}}
        assert schema.server_name is None

    def test_create_with_all_fields(self) -> None:
        """ToolSchema can be created with all fields including server_name."""
        schema = ToolSchema(
            name="create_task",
            description="Create a new task",
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                },
                "required": ["title"],
            },
            server_name="gobby-tasks",
        )

        assert schema.name == "create_task"
        assert schema.description == "Create a new task"
        assert schema.server_name == "gobby-tasks"
        assert schema.input_schema["required"] == ["title"]

    def test_complex_input_schema(self) -> None:
        """ToolSchema handles complex input schemas."""
        schema = ToolSchema(
            name="complex_tool",
            description="A complex tool",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name"},
                    "count": {"type": "integer", "minimum": 0},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "metadata": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                },
                "required": ["name"],
            },
        )

        assert schema.input_schema["properties"]["tags"]["type"] == "array"
        assert schema.input_schema["properties"]["count"]["minimum"] == 0


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_create_success_result(self) -> None:
        """ToolResult can represent a successful call."""
        result = ToolResult(
            tool_name="test_tool",
            success=True,
            result={"data": "value"},
        )

        assert result.tool_name == "test_tool"
        assert result.success is True
        assert result.result == {"data": "value"}
        assert result.error is None

    def test_create_error_result(self) -> None:
        """ToolResult can represent a failed call."""
        result = ToolResult(
            tool_name="test_tool",
            success=False,
            error="Something went wrong",
        )

        assert result.tool_name == "test_tool"
        assert result.success is False
        assert result.result is None
        assert result.error == "Something went wrong"

    def test_success_with_none_result(self) -> None:
        """ToolResult can succeed with None result."""
        result = ToolResult(
            tool_name="void_tool",
            success=True,
        )

        assert result.success is True
        assert result.result is None
        assert result.error is None

    def test_result_with_complex_data(self) -> None:
        """ToolResult handles complex result data."""
        result = ToolResult(
            tool_name="data_tool",
            success=True,
            result={
                "items": [1, 2, 3],
                "nested": {"a": {"b": "c"}},
                "count": 100,
            },
        )

        assert result.result["items"] == [1, 2, 3]
        assert result.result["nested"]["a"]["b"] == "c"


class TestToolCallRecord:
    """Tests for ToolCallRecord dataclass."""

    def test_create_without_result(self) -> None:
        """ToolCallRecord can be created without result."""
        record = ToolCallRecord(
            tool_name="test_tool",
            arguments={"arg1": "value1"},
        )

        assert record.tool_name == "test_tool"
        assert record.arguments == {"arg1": "value1"}
        assert record.result is None

    def test_create_with_result(self) -> None:
        """ToolCallRecord can be created with result."""
        result = ToolResult(tool_name="test_tool", success=True, result={"ok": True})

        record = ToolCallRecord(
            tool_name="test_tool",
            arguments={"arg1": "value1"},
            result=result,
        )

        assert record.tool_name == "test_tool"
        assert record.result is result
        assert record.result.success is True

    def test_empty_arguments(self) -> None:
        """ToolCallRecord handles empty arguments."""
        record = ToolCallRecord(
            tool_name="no_args_tool",
            arguments={},
        )

        assert record.arguments == {}


class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_create_success_result(self) -> None:
        """AgentResult can represent successful execution."""
        result = AgentResult(
            output="Task completed successfully.",
            status="success",
            turns_used=3,
        )

        assert result.output == "Task completed successfully."
        assert result.status == "success"
        assert result.turns_used == 3
        assert result.tool_calls == []
        assert result.artifacts == {}
        assert result.files_modified == []
        assert result.next_steps == []
        assert result.error is None
        assert result.run_id is None

    def test_create_with_all_fields(self) -> None:
        """AgentResult can be created with all fields."""
        tool_call = ToolCallRecord(
            tool_name="edit",
            arguments={"file": "test.py"},
            result=ToolResult(tool_name="edit", success=True),
        )

        result = AgentResult(
            output="Feature implemented.",
            status="success",
            tool_calls=[tool_call],
            artifacts={"plan": "implementation steps"},
            files_modified=["src/main.py", "tests/test_main.py"],
            next_steps=["Run tests", "Deploy"],
            turns_used=5,
            run_id="run-abc123",
        )

        assert result.output == "Feature implemented."
        assert result.status == "success"
        assert len(result.tool_calls) == 1
        assert result.artifacts == {"plan": "implementation steps"}
        assert len(result.files_modified) == 2
        assert len(result.next_steps) == 2
        assert result.run_id == "run-abc123"

    def test_create_error_result(self) -> None:
        """AgentResult can represent error."""
        result = AgentResult(
            output="",
            status="error",
            error="Connection refused",
            turns_used=1,
        )

        assert result.status == "error"
        assert result.error == "Connection refused"
        assert result.output == ""

    def test_create_timeout_result(self) -> None:
        """AgentResult can represent timeout."""
        result = AgentResult(
            output="",
            status="timeout",
            error="Execution timed out after 120s",
            turns_used=10,
        )

        assert result.status == "timeout"
        assert "timed out" in result.error

    def test_create_partial_result(self) -> None:
        """AgentResult can represent partial completion."""
        result = AgentResult(
            output="Completed 3 of 5 tasks.",
            status="partial",
            turns_used=10,
        )

        assert result.status == "partial"

    def test_create_blocked_result(self) -> None:
        """AgentResult can represent blocked status."""
        result = AgentResult(
            output="Blocked by missing dependency.",
            status="blocked",
            turns_used=2,
        )

        assert result.status == "blocked"

    def test_valid_status_values(self) -> None:
        """AgentResult accepts all valid status values."""
        valid_statuses = ["success", "partial", "blocked", "timeout", "error"]

        for status in valid_statuses:
            result = AgentResult(output="", status=status)  # type: ignore[arg-type]
            assert result.status == status


class TestAgentExecutorRunWithCompleteTool:
    """Tests for AgentExecutor.run_with_complete_tool() method."""

    class MockExecutor(AgentExecutor):
        """Mock executor for testing run_with_complete_tool."""

        def __init__(self):
            self.run_calls: list[dict] = []
            self.mock_result = AgentResult(output="Default", status="success")

        @property
        def provider_name(self) -> str:
            return "mock"

        async def run(
            self,
            prompt: str,
            tools: list[ToolSchema],
            tool_handler: ToolHandler,
            system_prompt: str | None = None,
            model: str | None = None,
            max_turns: int = 10,
            timeout: float = 120.0,
        ) -> AgentResult:
            self.run_calls.append(
                {
                    "prompt": prompt,
                    "tools": tools,
                    "tool_handler": tool_handler,
                    "system_prompt": system_prompt,
                    "model": model,
                    "max_turns": max_turns,
                    "timeout": timeout,
                }
            )
            return self.mock_result

    @pytest.fixture
    def executor(self):
        """Create a mock executor."""
        return self.MockExecutor()

    @pytest.fixture
    def simple_tools(self):
        """Create simple tool schemas for testing."""
        return [
            ToolSchema(
                name="get_weather",
                description="Get weather",
                input_schema={"type": "object", "properties": {}},
            ),
        ]

    async def test_adds_complete_tool(self, executor, simple_tools):
        """run_with_complete_tool adds complete tool to tools list."""

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True)

        await executor.run_with_complete_tool(
            prompt="Test",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        assert len(executor.run_calls) == 1
        tools_passed = executor.run_calls[0]["tools"]
        assert len(tools_passed) == 2  # Original + complete

        complete_tool = next(t for t in tools_passed if t.name == "complete")
        assert complete_tool is not None
        assert "Signal that you have completed" in complete_tool.description

    async def test_complete_tool_schema(self, executor, simple_tools):
        """Complete tool has correct schema."""

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True)

        await executor.run_with_complete_tool(
            prompt="Test",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        tools_passed = executor.run_calls[0]["tools"]
        complete_tool = next(t for t in tools_passed if t.name == "complete")

        schema = complete_tool.input_schema
        assert schema["type"] == "object"
        assert "output" in schema["properties"]
        assert "status" in schema["properties"]
        assert "artifacts" in schema["properties"]
        assert "files_modified" in schema["properties"]
        assert "next_steps" in schema["properties"]
        assert schema["required"] == ["output"]

    async def test_returns_result_from_complete_call(self, executor, simple_tools):
        """run_with_complete_tool returns result from complete() call."""
        completion_captured: list[dict] = []

        async def handler_that_calls_complete(name: str, args: dict) -> ToolResult:
            if name == "complete":
                completion_captured.append(args)
                return ToolResult(tool_name="complete", success=True, result="Task completed.")
            return ToolResult(tool_name=name, success=True)

        # Create an executor that simulates calling the complete tool
        class CompletingExecutor(self.MockExecutor):
            async def run(
                self,
                prompt: str,
                tools: list[ToolSchema],
                tool_handler: ToolHandler,
                **kwargs,
            ) -> AgentResult:
                # Simulate calling the complete tool
                await tool_handler(
                    "complete",
                    {
                        "output": "Successfully completed",
                        "status": "success",
                        "artifacts": {"key": "value"},
                        "files_modified": ["test.py"],
                        "next_steps": ["Review code"],
                    },
                )
                return AgentResult(
                    output="",
                    status="success",
                    tool_calls=[ToolCallRecord(tool_name="complete", arguments={})],
                    turns_used=1,
                )

        completing_executor = CompletingExecutor()

        result = await completing_executor.run_with_complete_tool(
            prompt="Test",
            tools=simple_tools,
            tool_handler=handler_that_calls_complete,
        )

        assert result.output == "Successfully completed"
        assert result.status == "success"
        assert result.artifacts == {"key": "value"}
        assert result.files_modified == ["test.py"]
        assert result.next_steps == ["Review code"]
        assert result.turns_used == 1

    async def test_returns_raw_result_without_complete_call(self, executor, simple_tools):
        """run_with_complete_tool returns raw result if complete() not called."""
        executor.mock_result = AgentResult(
            output="Raw output",
            status="timeout",
            error="Timed out",
            turns_used=10,
        )

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True)

        result = await executor.run_with_complete_tool(
            prompt="Test",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        assert result.status == "timeout"
        assert result.output == "Raw output"
        assert result.error == "Timed out"

    async def test_delegates_to_original_handler(self, executor, simple_tools):
        """run_with_complete_tool delegates non-complete tools to original handler."""
        handler_calls: list[str] = []

        async def tracking_handler(name: str, args: dict) -> ToolResult:
            handler_calls.append(name)
            return ToolResult(tool_name=name, success=True, result={"tracked": True})

        # Create executor that calls the original tool
        class DelegatingExecutor(self.MockExecutor):
            async def run(
                self,
                prompt: str,
                tools: list[ToolSchema],
                tool_handler: ToolHandler,
                **kwargs,
            ) -> AgentResult:
                # Simulate calling a regular tool
                result = await tool_handler("get_weather", {"location": "SF"})
                return AgentResult(
                    output="Done",
                    status="success",
                    tool_calls=[
                        ToolCallRecord(
                            tool_name="get_weather",
                            arguments={"location": "SF"},
                            result=result,
                        )
                    ],
                    turns_used=1,
                )

        delegating_executor = DelegatingExecutor()

        result = await delegating_executor.run_with_complete_tool(
            prompt="Test",
            tools=simple_tools,
            tool_handler=tracking_handler,
        )

        assert "get_weather" in handler_calls
        assert result.tool_calls[0].result.result == {"tracked": True}

    async def test_passes_through_all_parameters(self, executor, simple_tools):
        """run_with_complete_tool passes all parameters to run()."""

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True)

        await executor.run_with_complete_tool(
            prompt="Test prompt",
            tools=simple_tools,
            tool_handler=dummy_handler,
            system_prompt="Custom system prompt",
            model="custom-model",
            max_turns=5,
            timeout=60.0,
        )

        call = executor.run_calls[0]
        assert call["prompt"] == "Test prompt"
        assert call["system_prompt"] == "Custom system prompt"
        assert call["model"] == "custom-model"
        assert call["max_turns"] == 5
        assert call["timeout"] == 60.0

    async def test_validates_complete_status(self, simple_tools):
        """run_with_complete_tool validates status from complete() call."""

        class ValidatingExecutor(self.MockExecutor):
            async def run(
                self,
                prompt: str,
                tools: list[ToolSchema],
                tool_handler: ToolHandler,
                **kwargs,
            ) -> AgentResult:
                # Simulate calling complete with invalid status
                await tool_handler(
                    "complete",
                    {
                        "output": "Done",
                        "status": "invalid_status",  # Invalid
                    },
                )
                return AgentResult(output="", status="success", turns_used=1)

        executor = ValidatingExecutor()

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True)

        result = await executor.run_with_complete_tool(
            prompt="Test",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        # Invalid status should default to "success"
        assert result.status == "success"

    async def test_complete_partial_status(self, simple_tools):
        """run_with_complete_tool accepts 'partial' status."""

        class PartialExecutor(self.MockExecutor):
            async def run(
                self,
                prompt: str,
                tools: list[ToolSchema],
                tool_handler: ToolHandler,
                **kwargs,
            ) -> AgentResult:
                await tool_handler(
                    "complete",
                    {
                        "output": "Partial progress",
                        "status": "partial",
                    },
                )
                return AgentResult(output="", status="success", turns_used=1)

        executor = PartialExecutor()

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True)

        result = await executor.run_with_complete_tool(
            prompt="Test",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        assert result.status == "partial"

    async def test_complete_blocked_status(self, simple_tools):
        """run_with_complete_tool accepts 'blocked' status."""

        class BlockedExecutor(self.MockExecutor):
            async def run(
                self,
                prompt: str,
                tools: list[ToolSchema],
                tool_handler: ToolHandler,
                **kwargs,
            ) -> AgentResult:
                await tool_handler(
                    "complete",
                    {
                        "output": "Blocked by dependency",
                        "status": "blocked",
                    },
                )
                return AgentResult(output="", status="success", turns_used=1)

        executor = BlockedExecutor()

        async def dummy_handler(name: str, args: dict) -> ToolResult:
            return ToolResult(tool_name=name, success=True)

        result = await executor.run_with_complete_tool(
            prompt="Test",
            tools=simple_tools,
            tool_handler=dummy_handler,
        )

        assert result.status == "blocked"


class TestToolHandlerType:
    """Tests for the ToolHandler type alias."""

    async def test_tool_handler_signature(self):
        """ToolHandler has correct signature."""
        # This tests that the type alias works correctly

        async def handler(tool_name: str, arguments: dict) -> ToolResult:
            return ToolResult(tool_name=tool_name, success=True, result=arguments)

        # Type check: This should compile without errors
        _typed_handler: ToolHandler = handler

        result = await _typed_handler("test", {"key": "value"})
        assert result.tool_name == "test"
        assert result.result == {"key": "value"}
