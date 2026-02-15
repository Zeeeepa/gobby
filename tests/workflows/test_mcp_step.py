"""Tests for MCP step type in pipeline definitions and executor.

Tests MCPStepConfig model, PipelineStep with mcp field,
_execute_mcp_step, and template rendering with type coercion.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from gobby.workflows.definitions import MCPStepConfig, PipelineStep

pytestmark = pytest.mark.unit


# =============================================================================
# MCPStepConfig model tests
# =============================================================================


class TestMCPStepConfig:
    """Tests for MCPStepConfig Pydantic model."""

    def test_minimal_config(self) -> None:
        """Test creating config with required fields only."""
        config = MCPStepConfig(server="gobby-tasks", tool="suggest_next_task")
        assert config.server == "gobby-tasks"
        assert config.tool == "suggest_next_task"
        assert config.arguments is None

    def test_config_with_arguments(self) -> None:
        """Test creating config with arguments."""
        config = MCPStepConfig(
            server="gobby-agents",
            tool="spawn_agent",
            arguments={"prompt": "Do work", "agent": "developer-gemini", "timeout": 600},
        )
        assert config.server == "gobby-agents"
        assert config.tool == "spawn_agent"
        assert config.arguments["prompt"] == "Do work"
        assert config.arguments["timeout"] == 600

    def test_config_empty_arguments(self) -> None:
        """Test config with explicit empty dict arguments."""
        config = MCPStepConfig(server="s", tool="t", arguments={})
        assert config.arguments == {}

    def test_config_requires_server(self) -> None:
        """Test that server is required."""
        with pytest.raises(ValidationError):
            MCPStepConfig(tool="some_tool")  # type: ignore

    def test_config_requires_tool(self) -> None:
        """Test that tool is required."""
        with pytest.raises(ValidationError):
            MCPStepConfig(server="some_server")  # type: ignore


# =============================================================================
# PipelineStep with mcp field tests
# =============================================================================


class TestPipelineStepMCP:
    """Tests for PipelineStep with mcp execution type."""

    def test_mcp_step(self) -> None:
        """Test creating a step with mcp field."""
        step = PipelineStep(
            id="find_work",
            mcp=MCPStepConfig(
                server="gobby-tasks",
                tool="suggest_next_task",
                arguments={"parent_task_id": "#123"},
            ),
        )
        assert step.id == "find_work"
        assert step.mcp is not None
        assert step.mcp.server == "gobby-tasks"
        assert step.mcp.tool == "suggest_next_task"
        assert step.exec is None
        assert step.prompt is None
        assert step.invoke_pipeline is None

    def test_mcp_mutually_exclusive_with_exec(self) -> None:
        """Test that mcp and exec are mutually exclusive."""
        with pytest.raises(ValidationError) as exc_info:
            PipelineStep(
                id="invalid",
                exec="echo hello",
                mcp=MCPStepConfig(server="s", tool="t"),
            )
        assert (
            "mutually exclusive" in str(exc_info.value).lower()
            or "only one" in str(exc_info.value).lower()
        )

    def test_mcp_mutually_exclusive_with_prompt(self) -> None:
        """Test that mcp and prompt are mutually exclusive."""
        with pytest.raises(ValidationError) as exc_info:
            PipelineStep(
                id="invalid",
                prompt="Do something",
                mcp=MCPStepConfig(server="s", tool="t"),
            )
        assert (
            "mutually exclusive" in str(exc_info.value).lower()
            or "only one" in str(exc_info.value).lower()
        )

    def test_mcp_mutually_exclusive_with_invoke_pipeline(self) -> None:
        """Test that mcp and invoke_pipeline are mutually exclusive."""
        with pytest.raises(ValidationError) as exc_info:
            PipelineStep(
                id="invalid",
                invoke_pipeline="other-pipeline",
                mcp=MCPStepConfig(server="s", tool="t"),
            )
        assert (
            "mutually exclusive" in str(exc_info.value).lower()
            or "only one" in str(exc_info.value).lower()
        )

    def test_mcp_step_with_condition(self) -> None:
        """Test mcp step with condition."""
        step = PipelineStep(
            id="conditional_mcp",
            mcp=MCPStepConfig(server="s", tool="t"),
            condition="steps.prev.output.task_id",
        )
        assert step.condition is not None
        assert step.mcp is not None


# =============================================================================
# Pipeline executor MCP step execution tests
# =============================================================================


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_execution_manager():
    manager = MagicMock()
    mock_execution = MagicMock()
    mock_execution.id = "pe-test-123"
    mock_step = MagicMock()
    mock_step.id = 1
    manager.create_execution.return_value = mock_execution
    manager.get_execution.return_value = mock_execution
    manager.update_execution_status.return_value = mock_execution
    manager.create_step_execution.return_value = mock_step
    manager.update_step_execution.return_value = mock_step
    return manager


@pytest.fixture
def mock_llm_service():
    return AsyncMock()


@pytest.fixture
def mock_tool_proxy():
    proxy = AsyncMock()
    proxy.call_tool = AsyncMock(return_value={"success": True, "task_id": "#42"})
    return proxy


class TestExecuteMCPStep:
    """Tests for PipelineExecutor._execute_mcp_step."""

    @pytest.mark.asyncio
    async def test_mcp_step_calls_tool_proxy(
        self, mock_db, mock_execution_manager, mock_llm_service, mock_tool_proxy
    ) -> None:
        """Test that MCP step calls tool_proxy.call_tool with correct args."""
        from gobby.workflows.pipeline_executor import PipelineExecutor

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
            tool_proxy_getter=lambda: mock_tool_proxy,
        )

        step = PipelineStep(
            id="test_step",
            mcp=MCPStepConfig(
                server="gobby-tasks",
                tool="suggest_next_task",
                arguments={"parent_task_id": "#123"},
            ),
        )

        context: dict = {"inputs": {}, "steps": {}}
        result = await executor._execute_mcp_step(step, context)

        mock_tool_proxy.call_tool.assert_called_once_with(
            "gobby-tasks", "suggest_next_task", {"parent_task_id": "#123"}
        )
        assert result["success"] is True
        assert result["task_id"] == "#42"

    @pytest.mark.asyncio
    async def test_mcp_step_no_arguments(
        self, mock_db, mock_execution_manager, mock_llm_service, mock_tool_proxy
    ) -> None:
        """Test MCP step with no arguments passes empty dict."""
        from gobby.workflows.pipeline_executor import PipelineExecutor

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
            tool_proxy_getter=lambda: mock_tool_proxy,
        )

        step = PipelineStep(
            id="test_step",
            mcp=MCPStepConfig(server="gobby-agents", tool="wait_for_agent"),
        )

        context: dict = {"inputs": {}, "steps": {}}
        await executor._execute_mcp_step(step, context)

        mock_tool_proxy.call_tool.assert_called_once_with("gobby-agents", "wait_for_agent", {})

    @pytest.mark.asyncio
    async def test_mcp_step_raises_without_tool_proxy_getter(
        self, mock_db, mock_execution_manager, mock_llm_service
    ) -> None:
        """Test that MCP step raises RuntimeError without tool_proxy_getter."""
        from gobby.workflows.pipeline_executor import PipelineExecutor

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
            # No tool_proxy_getter
        )

        step = PipelineStep(
            id="test_step",
            mcp=MCPStepConfig(server="s", tool="t"),
        )

        context: dict = {"inputs": {}, "steps": {}}
        with pytest.raises(RuntimeError, match="requires tool_proxy_getter"):
            await executor._execute_mcp_step(step, context)

    @pytest.mark.asyncio
    async def test_mcp_step_raises_when_tool_proxy_returns_none(
        self, mock_db, mock_execution_manager, mock_llm_service
    ) -> None:
        """Test that MCP step raises when tool_proxy_getter returns None."""
        from gobby.workflows.pipeline_executor import PipelineExecutor

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
            tool_proxy_getter=lambda: None,
        )

        step = PipelineStep(
            id="test_step",
            mcp=MCPStepConfig(server="s", tool="t"),
        )

        context: dict = {"inputs": {}, "steps": {}}
        with pytest.raises(RuntimeError, match="returned None"):
            await executor._execute_mcp_step(step, context)

    @pytest.mark.asyncio
    async def test_mcp_step_raises_on_failure_result(
        self, mock_db, mock_execution_manager, mock_llm_service
    ) -> None:
        """Test that MCP step raises RuntimeError when result has success=False."""
        from gobby.workflows.pipeline_executor import PipelineExecutor

        mock_proxy = AsyncMock()
        mock_proxy.call_tool = AsyncMock(return_value={"success": False, "error": "Tool not found"})

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
            tool_proxy_getter=lambda: mock_proxy,
        )

        step = PipelineStep(
            id="failing_step",
            mcp=MCPStepConfig(server="s", tool="missing_tool"),
        )

        context: dict = {"inputs": {}, "steps": {}}
        with pytest.raises(RuntimeError, match="failed"):
            await executor._execute_mcp_step(step, context)


class TestMCPStepInPipelineExecute:
    """Tests for MCP step execution within full pipeline execute flow."""

    @pytest.mark.asyncio
    async def test_mcp_step_executes_in_pipeline(
        self, mock_db, mock_execution_manager, mock_llm_service, mock_tool_proxy
    ) -> None:
        """Test that MCP steps execute correctly within the pipeline flow."""
        from gobby.workflows.definitions import PipelineDefinition
        from gobby.workflows.pipeline_executor import PipelineExecutor

        pipeline = PipelineDefinition(
            name="mcp-pipeline",
            steps=[
                PipelineStep(
                    id="mcp_step",
                    mcp=MCPStepConfig(
                        server="gobby-tasks",
                        tool="suggest_next_task",
                    ),
                ),
            ],
        )

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
            tool_proxy_getter=lambda: mock_tool_proxy,
        )

        await executor.execute(pipeline=pipeline, inputs={}, project_id="proj-123")

        mock_tool_proxy.call_tool.assert_called_once()
        mock_execution_manager.create_step_execution.assert_called_once()


# =============================================================================
# Template rendering + type coercion tests
# =============================================================================


class TestMCPTemplateRendering:
    """Tests for template rendering in MCP step arguments with type coercion."""

    @pytest.mark.asyncio
    async def test_render_mcp_arguments_with_template(
        self, mock_db, mock_execution_manager, mock_llm_service, mock_tool_proxy
    ) -> None:
        """Test that ${{ }} templates are rendered in MCP arguments."""
        from gobby.workflows.pipeline_executor import PipelineExecutor
        from gobby.workflows.templates import TemplateEngine

        template_engine = TemplateEngine()

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
            template_engine=template_engine,
            tool_proxy_getter=lambda: mock_tool_proxy,
        )

        step = PipelineStep(
            id="templated_step",
            mcp=MCPStepConfig(
                server="gobby-agents",
                tool="spawn_agent",
                arguments={
                    "prompt": "Work on ${{ inputs.task_title }}",
                    "timeout": "${{ inputs.wait_timeout }}",
                },
            ),
        )

        context: dict = {
            "inputs": {"task_title": "Fix bug #42", "wait_timeout": "600"},
            "steps": {},
        }

        rendered = executor._render_step(step, context)

        # String value should be rendered
        assert rendered.mcp.arguments["prompt"] == "Work on Fix bug #42"
        # Numeric string should be coerced to int
        assert rendered.mcp.arguments["timeout"] == 600
        assert isinstance(rendered.mcp.arguments["timeout"], int)

    @pytest.mark.asyncio
    async def test_coerce_boolean_values(
        self, mock_db, mock_execution_manager, mock_llm_service
    ) -> None:
        """Test that boolean strings are coerced to bool."""
        from gobby.workflows.pipeline_executor import PipelineExecutor
        from gobby.workflows.templates import TemplateEngine

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
            template_engine=TemplateEngine(),
        )

        step = PipelineStep(
            id="bool_step",
            mcp=MCPStepConfig(
                server="s",
                tool="t",
                arguments={
                    "force": "${{ inputs.force_flag }}",
                    "verbose": "${{ inputs.verbose }}",
                },
            ),
        )

        context: dict = {
            "inputs": {"force_flag": "true", "verbose": "false"},
            "steps": {},
        }

        rendered = executor._render_step(step, context)
        assert rendered.mcp.arguments["force"] is True
        assert rendered.mcp.arguments["verbose"] is False

    @pytest.mark.asyncio
    async def test_coerce_null_values(
        self, mock_db, mock_execution_manager, mock_llm_service
    ) -> None:
        """Test that null/none strings are coerced to None."""
        from gobby.workflows.pipeline_executor import PipelineExecutor
        from gobby.workflows.templates import TemplateEngine

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
            template_engine=TemplateEngine(),
        )

        step = PipelineStep(
            id="null_step",
            mcp=MCPStepConfig(
                server="s",
                tool="t",
                arguments={"param": "${{ inputs.maybe_null }}"},
            ),
        )

        context: dict = {
            "inputs": {"maybe_null": "null"},
            "steps": {},
        }

        rendered = executor._render_step(step, context)
        assert rendered.mcp.arguments["param"] is None

    @pytest.mark.asyncio
    async def test_coerce_float_values(
        self, mock_db, mock_execution_manager, mock_llm_service
    ) -> None:
        """Test that float strings are coerced to float."""
        from gobby.workflows.pipeline_executor import PipelineExecutor
        from gobby.workflows.templates import TemplateEngine

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
            template_engine=TemplateEngine(),
        )

        step = PipelineStep(
            id="float_step",
            mcp=MCPStepConfig(
                server="s",
                tool="t",
                arguments={"ratio": "${{ inputs.ratio }}"},
            ),
        )

        context: dict = {
            "inputs": {"ratio": "0.75"},
            "steps": {},
        }

        rendered = executor._render_step(step, context)
        assert rendered.mcp.arguments["ratio"] == 0.75
        assert isinstance(rendered.mcp.arguments["ratio"], float)

    @pytest.mark.asyncio
    async def test_nested_dict_arguments_rendered(
        self, mock_db, mock_execution_manager, mock_llm_service
    ) -> None:
        """Test that nested dict arguments are recursively rendered."""
        from gobby.workflows.pipeline_executor import PipelineExecutor
        from gobby.workflows.templates import TemplateEngine

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
            template_engine=TemplateEngine(),
        )

        step = PipelineStep(
            id="nested_step",
            mcp=MCPStepConfig(
                server="s",
                tool="t",
                arguments={
                    "outer": {
                        "inner_str": "${{ inputs.name }}",
                        "inner_num": "${{ inputs.count }}",
                    }
                },
            ),
        )

        context: dict = {
            "inputs": {"name": "test", "count": "5"},
            "steps": {},
        }

        rendered = executor._render_step(step, context)
        assert rendered.mcp.arguments["outer"]["inner_str"] == "test"
        assert rendered.mcp.arguments["outer"]["inner_num"] == 5

    @pytest.mark.asyncio
    async def test_render_does_not_mutate_original(
        self, mock_db, mock_execution_manager, mock_llm_service
    ) -> None:
        """Test that rendering doesn't mutate the original step definition."""
        from gobby.workflows.pipeline_executor import PipelineExecutor
        from gobby.workflows.templates import TemplateEngine

        executor = PipelineExecutor(
            db=mock_db,
            execution_manager=mock_execution_manager,
            llm_service=mock_llm_service,
            template_engine=TemplateEngine(),
        )

        original_args = {"timeout": "${{ inputs.timeout }}"}
        step = PipelineStep(
            id="immutable_step",
            mcp=MCPStepConfig(server="s", tool="t", arguments=original_args),
        )

        context: dict = {"inputs": {"timeout": "300"}, "steps": {}}
        rendered = executor._render_step(step, context)

        # Original should be unchanged
        assert step.mcp.arguments["timeout"] == "${{ inputs.timeout }}"
        # Rendered should have coerced value
        assert rendered.mcp.arguments["timeout"] == 300
