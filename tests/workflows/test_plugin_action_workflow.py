"""
Tests for plugin action execution within workflows.

These tests verify that plugin-defined actions can be executed within
workflow definitions, receiving proper context and producing expected results.
"""

from unittest.mock import MagicMock

import pytest

from gobby.hooks.plugins import HookPlugin, PluginRegistry
from gobby.workflows.actions import ActionContext, ActionExecutor
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.engine import WorkflowEngine
from gobby.workflows.evaluator import ConditionEvaluator
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager

# =============================================================================
# Test Plugin Fixtures
# =============================================================================


class WorkflowTestPlugin(HookPlugin):
    """Plugin with actions designed for workflow testing."""

    name = "workflow-test"
    version = "1.0.0"

    def __init__(self):
        super().__init__()
        self.action_calls = []  # Track calls for assertions

    def on_load(self, config: dict) -> None:
        self.config = config
        self.register_action("track_call", self._track_call)
        self.register_action("modify_state", self._modify_state)
        self.register_action("inject_context", self._inject_context)
        self.register_action("slow_action", self._slow_action)
        self.register_action("failing_action", self._failing_action)

    async def _track_call(self, context: ActionContext, **kwargs) -> dict:
        """Track that this action was called with context."""
        self.action_calls.append(
            {
                "action": "track_call",
                "session_id": context.session_id,
                "workflow_name": context.state.workflow_name if context.state else None,
                "step": context.state.step if context.state else None,
                "kwargs": kwargs,
            }
        )
        return {"tracked": True, "call_count": len(self.action_calls)}

    async def _modify_state(self, context: ActionContext, **kwargs) -> dict:
        """Modify workflow state variables."""
        var_name = kwargs.get("variable", "test_var")
        var_value = kwargs.get("value", "modified")

        if context.state and context.state.variables is not None:
            context.state.variables[var_name] = var_value

        self.action_calls.append(
            {
                "action": "modify_state",
                "variable": var_name,
                "value": var_value,
            }
        )
        return {"modified": True, "variable": var_name, "value": var_value}

    async def _inject_context(self, context: ActionContext, **kwargs) -> dict:
        """Return context for injection into workflow."""
        message = kwargs.get("message", "Injected by plugin")
        return {"inject_context": message}

    async def _slow_action(self, context: ActionContext, **kwargs) -> dict:
        """Simulate a slow action for timeout testing."""
        import asyncio

        delay = kwargs.get("delay", 0.1)
        await asyncio.sleep(delay)
        return {"completed": True, "delay": delay}

    async def _failing_action(self, context: ActionContext, **kwargs) -> dict:
        """Action that raises an error."""
        error_msg = kwargs.get("error_message", "Intentional test failure")
        raise RuntimeError(error_msg)


class StateModifyingPlugin(HookPlugin):
    """Plugin that modifies workflow state in various ways."""

    name = "state-modifier"

    def on_load(self, config: dict) -> None:
        self.register_action("set_artifact", self._set_artifact)
        self.register_action("add_observation", self._add_observation)

    async def _set_artifact(self, context: ActionContext, **kwargs) -> dict:
        """Set an artifact in workflow state."""
        name = kwargs.get("name", "test_artifact")
        path = kwargs.get("path", "/test/path")
        if context.state:
            context.state.artifacts[name] = path
        return {"artifact_set": name}

    async def _add_observation(self, context: ActionContext, **kwargs) -> dict:
        """Add an observation to workflow state."""
        observation = kwargs.get("observation", {"type": "test"})
        if context.state:
            context.state.observations.append(observation)
        return {"observation_added": True}


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Create mock database."""
    return MagicMock()


@pytest.fixture
def mock_session_manager():
    """Create mock session manager."""
    manager = MagicMock()
    manager.get.return_value = MagicMock(project_id="test-project")
    return manager


@pytest.fixture
def mock_template_engine():
    """Create mock template engine."""
    engine = MagicMock()
    engine.render.side_effect = lambda t, c: t
    return engine


@pytest.fixture
def workflow_test_plugin():
    """Create and load test plugin."""
    plugin = WorkflowTestPlugin()
    plugin.on_load({})
    return plugin


@pytest.fixture
def plugin_registry(workflow_test_plugin):
    """Create registry with test plugin."""
    registry = PluginRegistry()
    registry.register_plugin(workflow_test_plugin)
    return registry


@pytest.fixture
def action_executor(mock_db, mock_session_manager, mock_template_engine, plugin_registry):
    """Create ActionExecutor with plugin actions registered."""
    executor = ActionExecutor(
        db=mock_db,
        session_manager=mock_session_manager,
        template_engine=mock_template_engine,
    )
    executor.register_plugin_actions(plugin_registry)
    return executor


@pytest.fixture
def workflow_state():
    """Create a workflow state for testing."""
    return WorkflowState(
        session_id="test-session-123",
        workflow_name="test-workflow",
        step="execute",
        variables={"initial_var": "initial_value"},
    )


@pytest.fixture
def action_context(workflow_state, mock_db, mock_session_manager, mock_template_engine):
    """Create ActionContext for direct executor testing."""
    return ActionContext(
        session_id=workflow_state.session_id,
        state=workflow_state,
        db=mock_db,
        session_manager=mock_session_manager,
        template_engine=mock_template_engine,
    )


# =============================================================================
# Test Plugin Action Resolution
# =============================================================================


class TestPluginActionResolution:
    """Tests for plugin action type resolution in workflows."""

    def test_plugin_action_registered_with_correct_name(self, action_executor):
        """Plugin actions should be registered as plugin:name:action."""
        assert "plugin:workflow-test:track_call" in action_executor._handlers
        assert "plugin:workflow-test:modify_state" in action_executor._handlers
        assert "plugin:workflow-test:inject_context" in action_executor._handlers

    @pytest.mark.asyncio
    async def test_plugin_action_resolves_and_executes(
        self, action_executor, action_context, workflow_test_plugin
    ):
        """Workflow with plugin action type should resolve to plugin executor."""
        result = await action_executor.execute(
            "plugin:workflow-test:track_call",
            action_context,
            extra_param="test_value",
        )

        assert result is not None
        assert result["tracked"] is True
        assert len(workflow_test_plugin.action_calls) == 1
        assert workflow_test_plugin.action_calls[0]["kwargs"]["extra_param"] == "test_value"

    @pytest.mark.asyncio
    async def test_unknown_plugin_action_returns_none(self, action_executor, action_context):
        """Unknown action type should return None (graceful handling)."""
        result = await action_executor.execute(
            "plugin:nonexistent:action",
            action_context,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_unknown_builtin_action_returns_none(self, action_executor, action_context):
        """Unknown built-in action type should also return None."""
        result = await action_executor.execute(
            "completely_unknown_action_type",
            action_context,
        )

        assert result is None


# =============================================================================
# Test Plugin Action Context
# =============================================================================


class TestPluginActionContext:
    """Tests for plugin actions receiving proper workflow context."""

    @pytest.mark.asyncio
    async def test_plugin_action_receives_session_id(
        self, action_executor, action_context, workflow_test_plugin
    ):
        """Plugin action should receive correct session_id in context."""
        await action_executor.execute(
            "plugin:workflow-test:track_call",
            action_context,
        )

        assert len(workflow_test_plugin.action_calls) == 1
        assert workflow_test_plugin.action_calls[0]["session_id"] == "test-session-123"

    @pytest.mark.asyncio
    async def test_plugin_action_receives_workflow_state(
        self, action_executor, action_context, workflow_test_plugin
    ):
        """Plugin action should receive workflow name and step in context."""
        await action_executor.execute(
            "plugin:workflow-test:track_call",
            action_context,
        )

        call = workflow_test_plugin.action_calls[0]
        assert call["workflow_name"] == "test-workflow"
        assert call["step"] == "execute"

    @pytest.mark.asyncio
    async def test_plugin_action_receives_kwargs_from_workflow_def(
        self, action_executor, action_context, workflow_test_plugin
    ):
        """Plugin action should receive all kwargs from workflow action definition."""
        await action_executor.execute(
            "plugin:workflow-test:track_call",
            action_context,
            custom_param="custom_value",
            another_param=42,
            nested={"key": "value"},
        )

        kwargs = workflow_test_plugin.action_calls[0]["kwargs"]
        assert kwargs["custom_param"] == "custom_value"
        assert kwargs["another_param"] == 42
        assert kwargs["nested"]["key"] == "value"


# =============================================================================
# Test Plugin Action State Modification
# =============================================================================


class TestPluginActionStateModification:
    """Tests for plugin actions modifying workflow state."""

    @pytest.mark.asyncio
    async def test_plugin_action_modifies_state_variables(
        self, action_executor, action_context, workflow_state
    ):
        """Plugin action should be able to modify workflow state variables."""
        assert workflow_state.variables.get("new_variable") is None

        result = await action_executor.execute(
            "plugin:workflow-test:modify_state",
            action_context,
            variable="new_variable",
            value="new_value",
        )

        assert result["modified"] is True
        assert workflow_state.variables["new_variable"] == "new_value"

    @pytest.mark.asyncio
    async def test_plugin_action_state_changes_persist(
        self, action_executor, action_context, workflow_state
    ):
        """State changes made by plugin action should persist for subsequent actions."""
        # First action sets a variable
        await action_executor.execute(
            "plugin:workflow-test:modify_state",
            action_context,
            variable="counter",
            value=1,
        )

        assert workflow_state.variables["counter"] == 1

        # Second action can see the change
        await action_executor.execute(
            "plugin:workflow-test:modify_state",
            action_context,
            variable="counter",
            value=workflow_state.variables["counter"] + 1,
        )

        assert workflow_state.variables["counter"] == 2

    @pytest.mark.asyncio
    async def test_plugin_action_modifies_artifacts(
        self, mock_db, mock_session_manager, mock_template_engine, workflow_state
    ):
        """Plugin action should be able to modify workflow artifacts."""
        # Register state-modifier plugin
        registry = PluginRegistry()
        plugin = StateModifyingPlugin()
        plugin.on_load({})
        registry.register_plugin(plugin)

        executor = ActionExecutor(
            db=mock_db,
            session_manager=mock_session_manager,
            template_engine=mock_template_engine,
        )
        executor.register_plugin_actions(registry)

        context = ActionContext(
            session_id=workflow_state.session_id,
            state=workflow_state,
            db=mock_db,
            session_manager=mock_session_manager,
            template_engine=mock_template_engine,
        )

        await executor.execute(
            "plugin:state-modifier:set_artifact",
            context,
            name="output_file",
            path="/tmp/output.txt",
        )

        assert workflow_state.artifacts["output_file"] == "/tmp/output.txt"

    @pytest.mark.asyncio
    async def test_plugin_action_modifies_observations(
        self, mock_db, mock_session_manager, mock_template_engine, workflow_state
    ):
        """Plugin action should be able to add observations to workflow state."""
        registry = PluginRegistry()
        plugin = StateModifyingPlugin()
        plugin.on_load({})
        registry.register_plugin(plugin)

        executor = ActionExecutor(
            db=mock_db,
            session_manager=mock_session_manager,
            template_engine=mock_template_engine,
        )
        executor.register_plugin_actions(registry)

        context = ActionContext(
            session_id=workflow_state.session_id,
            state=workflow_state,
            db=mock_db,
            session_manager=mock_session_manager,
            template_engine=mock_template_engine,
        )

        initial_count = len(workflow_state.observations)

        await executor.execute(
            "plugin:state-modifier:add_observation",
            context,
            observation={"type": "metric", "value": 42},
        )

        assert len(workflow_state.observations) == initial_count + 1
        assert workflow_state.observations[-1] == {"type": "metric", "value": 42}


# =============================================================================
# Test Plugin Action Error Handling
# =============================================================================


class TestPluginActionErrorHandling:
    """Tests for error handling in plugin actions."""

    @pytest.mark.asyncio
    async def test_plugin_action_error_returns_error_dict(self, action_executor, action_context):
        """Plugin action errors should be caught and returned as error dict."""
        result = await action_executor.execute(
            "plugin:workflow-test:failing_action",
            action_context,
            error_message="Test failure message",
        )

        assert result is not None
        assert "error" in result
        assert "Test failure message" in result["error"]

    @pytest.mark.asyncio
    async def test_plugin_action_error_does_not_crash_executor(
        self, action_executor, action_context, workflow_test_plugin
    ):
        """Plugin action error should not prevent subsequent actions."""
        # First action fails
        result1 = await action_executor.execute(
            "plugin:workflow-test:failing_action",
            action_context,
        )
        assert "error" in result1

        # Second action should still work
        result2 = await action_executor.execute(
            "plugin:workflow-test:track_call",
            action_context,
        )
        assert result2["tracked"] is True

    @pytest.mark.asyncio
    async def test_plugin_action_error_contains_exception_details(
        self, action_executor, action_context
    ):
        """Error result should contain enough detail to debug the issue."""
        result = await action_executor.execute(
            "plugin:workflow-test:failing_action",
            action_context,
            error_message="Specific error details here",
        )

        assert "error" in result
        # Should contain the error message
        assert "Specific error details" in result["error"]


# =============================================================================
# Test Plugin Action Results
# =============================================================================


class TestPluginActionResults:
    """Tests for plugin action result handling."""

    @pytest.mark.asyncio
    async def test_plugin_action_inject_context_result(self, action_executor, action_context):
        """Plugin action returning inject_context should be recognized."""
        result = await action_executor.execute(
            "plugin:workflow-test:inject_context",
            action_context,
            message="Custom context message",
        )

        assert result is not None
        assert "inject_context" in result
        assert result["inject_context"] == "Custom context message"

    @pytest.mark.asyncio
    async def test_plugin_action_returns_complex_result(
        self, action_executor, action_context, workflow_test_plugin
    ):
        """Plugin action can return complex result structures."""
        result = await action_executor.execute(
            "plugin:workflow-test:track_call",
            action_context,
        )

        assert result is not None
        assert "tracked" in result
        assert "call_count" in result
        assert isinstance(result["call_count"], int)


# =============================================================================
# Test Multiple Plugin Actions in Sequence
# =============================================================================


class TestPluginActionSequence:
    """Tests for executing multiple plugin actions in sequence."""

    @pytest.mark.asyncio
    async def test_multiple_plugin_actions_execute_in_order(
        self, action_executor, action_context, workflow_test_plugin
    ):
        """Multiple plugin actions should execute in order."""
        # Execute three actions in sequence
        await action_executor.execute(
            "plugin:workflow-test:track_call",
            action_context,
            order=1,
        )
        await action_executor.execute(
            "plugin:workflow-test:track_call",
            action_context,
            order=2,
        )
        await action_executor.execute(
            "plugin:workflow-test:track_call",
            action_context,
            order=3,
        )

        assert len(workflow_test_plugin.action_calls) == 3
        assert workflow_test_plugin.action_calls[0]["kwargs"]["order"] == 1
        assert workflow_test_plugin.action_calls[1]["kwargs"]["order"] == 2
        assert workflow_test_plugin.action_calls[2]["kwargs"]["order"] == 3

    @pytest.mark.asyncio
    async def test_plugin_and_builtin_actions_can_mix(
        self, action_executor, action_context, workflow_test_plugin
    ):
        """Plugin actions should work alongside built-in actions."""
        # Execute plugin action
        result1 = await action_executor.execute(
            "plugin:workflow-test:track_call",
            action_context,
        )
        assert result1["tracked"] is True

        # Execute built-in action (set_variable is a built-in)
        result2 = await action_executor.execute(
            "set_variable",
            action_context,
            name="builtin_var",
            value="builtin_value",
        )
        # set_variable returns the variable info
        assert result2 is not None

        # Execute another plugin action
        result3 = await action_executor.execute(
            "plugin:workflow-test:track_call",
            action_context,
        )
        assert result3["call_count"] == 2


# =============================================================================
# Test Workflow Engine Integration (Simulated)
# =============================================================================


class TestWorkflowEngineIntegration:
    """Tests simulating WorkflowEngine executing plugin actions."""

    @pytest.fixture
    def mock_loader(self):
        """Create mock workflow loader."""
        loader = MagicMock(spec=WorkflowLoader)
        return loader

    @pytest.fixture
    def mock_state_manager(self):
        """Create mock state manager."""
        manager = MagicMock(spec=WorkflowStateManager)
        return manager

    @pytest.mark.asyncio
    async def test_engine_executes_plugin_action_via_action_executor(
        self,
        action_executor,
        workflow_state,
        workflow_test_plugin,
        mock_loader,
        mock_state_manager,
    ):
        """WorkflowEngine should execute plugin actions through ActionExecutor."""
        # Create engine with our action executor
        engine = WorkflowEngine(
            loader=mock_loader,
            state_manager=mock_state_manager,
            action_executor=action_executor,
            evaluator=ConditionEvaluator(),
        )

        # Simulate what _execute_actions does
        actions = [
            {"action": "plugin:workflow-test:track_call", "test_param": "from_workflow"},
        ]

        # Call the private method directly to test integration
        await engine._execute_actions(actions, workflow_state)

        # Verify plugin action was called
        assert len(workflow_test_plugin.action_calls) == 1
        assert workflow_test_plugin.action_calls[0]["kwargs"]["test_param"] == "from_workflow"
        assert workflow_test_plugin.action_calls[0]["session_id"] == workflow_state.session_id

    @pytest.mark.asyncio
    async def test_engine_handles_plugin_action_error(
        self,
        action_executor,
        workflow_state,
        mock_loader,
        mock_state_manager,
    ):
        """WorkflowEngine should handle plugin action errors gracefully."""
        engine = WorkflowEngine(
            loader=mock_loader,
            state_manager=mock_state_manager,
            action_executor=action_executor,
            evaluator=ConditionEvaluator(),
        )

        # Action list with a failing action
        actions = [
            {"action": "plugin:workflow-test:failing_action", "error_message": "Engine test error"},
        ]

        # Should not raise - errors are caught by ActionExecutor
        await engine._execute_actions(actions, workflow_state)

    @pytest.mark.asyncio
    async def test_engine_processes_inject_context_from_plugin(
        self,
        action_executor,
        workflow_state,
        mock_loader,
        mock_state_manager,
    ):
        """WorkflowEngine should recognize inject_context from plugin actions."""
        engine = WorkflowEngine(
            loader=mock_loader,
            state_manager=mock_state_manager,
            action_executor=action_executor,
            evaluator=ConditionEvaluator(),
        )

        actions = [
            {
                "action": "plugin:workflow-test:inject_context",
                "message": "Plugin context injection",
            },
        ]

        # The engine logs inject_context results
        # We're just verifying it doesn't crash
        await engine._execute_actions(actions, workflow_state)


# =============================================================================
# Test Plugin Action Timeout and Cancellation
# =============================================================================


class TestPluginActionTimeoutAndCancellation:
    """Tests for plugin action timeout and cancellation handling."""

    @pytest.mark.asyncio
    async def test_slow_plugin_action_can_be_cancelled(self, action_executor, action_context):
        """Plugin action can be cancelled via asyncio cancellation."""
        import asyncio

        # Start slow action but cancel it
        task = asyncio.create_task(
            action_executor.execute(
                "plugin:workflow-test:slow_action",
                action_context,
                delay=10.0,  # 10 second delay
            )
        )

        # Give it a moment to start, then cancel
        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_slow_plugin_action_respects_timeout(self, action_executor, action_context):
        """Plugin action respects asyncio.wait_for timeout."""
        import asyncio

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                action_executor.execute(
                    "plugin:workflow-test:slow_action",
                    action_context,
                    delay=10.0,  # 10 second delay
                ),
                timeout=0.05,  # 50ms timeout
            )

    @pytest.mark.asyncio
    async def test_fast_plugin_action_completes_before_timeout(
        self, action_executor, action_context
    ):
        """Fast plugin action completes successfully with timeout."""
        import asyncio

        result = await asyncio.wait_for(
            action_executor.execute(
                "plugin:workflow-test:slow_action",
                action_context,
                delay=0.01,  # 10ms delay
            ),
            timeout=1.0,  # 1 second timeout
        )

        assert result is not None
        assert result["completed"] is True

    @pytest.mark.asyncio
    async def test_plugin_action_cancellation_does_not_affect_subsequent_actions(
        self, action_executor, action_context, workflow_test_plugin
    ):
        """Cancelling one action does not prevent subsequent actions."""
        import asyncio

        # Start and cancel a slow action
        task = asyncio.create_task(
            action_executor.execute(
                "plugin:workflow-test:slow_action",
                action_context,
                delay=10.0,
            )
        )
        await asyncio.sleep(0.01)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Subsequent action should still work
        result = await action_executor.execute(
            "plugin:workflow-test:track_call",
            action_context,
        )

        assert result is not None
        assert result["tracked"] is True
        assert len(workflow_test_plugin.action_calls) == 1
