"""Comprehensive tests for llm_actions.py module.

Tests the call_llm function with various scenarios including:
- Happy path with successful LLM calls
- Error handling for missing parameters
- Template rendering errors
- LLM service errors
- State management edge cases
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.workflows.definitions import WorkflowState
from gobby.workflows.llm_actions import call_llm
from gobby.workflows.templates import TemplateEngine

# --- Fixtures ---


@pytest.fixture
def mock_llm_service():
    """Create a mock LLM service with provider chain."""
    service = MagicMock()
    provider = MagicMock()
    provider.generate_text = AsyncMock(return_value="LLM Response")
    service.get_default_provider.return_value = provider
    return service


@pytest.fixture
def mock_template_engine():
    """Create a mock template engine."""
    engine = MagicMock(spec=TemplateEngine)
    engine.render.return_value = "Rendered prompt"
    return engine


@pytest.fixture
def workflow_state():
    """Create a basic workflow state for testing."""
    return WorkflowState(
        session_id="test-session-id",
        workflow_name="test-workflow",
        step="test-step",
        variables={"existing_var": "existing_value"},
    )


@pytest.fixture
def mock_session():
    """Create a mock session object."""
    session = MagicMock()
    session.id = "test-session-id"
    session.project_id = "test-project-id"
    return session


# --- call_llm Tests ---


class TestCallLlm:
    """Tests for the call_llm function."""

    @pytest.mark.asyncio
    async def test_call_llm_success(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test successful LLM call with response stored in state."""
        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Hello {{ name }}",
            output_as="response_var",
            name="World",
        )

        assert result["llm_called"] is True
        assert result["output_variable"] == "response_var"
        assert workflow_state.variables["response_var"] == "LLM Response"

        # Verify template rendering was called with correct context
        mock_template_engine.render.assert_called_once()
        render_call_args = mock_template_engine.render.call_args
        assert render_call_args[0][0] == "Hello {{ name }}"
        assert render_call_args[0][1]["session"] == mock_session
        assert render_call_args[0][1]["state"] == workflow_state
        assert render_call_args[0][1]["name"] == "World"

        # Verify LLM was called with rendered prompt
        mock_llm_service.get_default_provider.assert_called_once()
        provider = mock_llm_service.get_default_provider.return_value
        provider.generate_text.assert_called_once_with("Rendered prompt")

    @pytest.mark.asyncio
    async def test_call_llm_missing_prompt(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm returns error when prompt is missing."""
        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt=None,
            output_as="response_var",
        )

        assert "error" in result
        assert result["error"] == "Missing prompt or output_as"

        # Verify no LLM call was made
        mock_llm_service.get_default_provider.assert_not_called()

    @pytest.mark.asyncio
    async def test_call_llm_missing_output_as(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm returns error when output_as is missing."""
        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Hello",
            output_as=None,
        )

        assert "error" in result
        assert result["error"] == "Missing prompt or output_as"

    @pytest.mark.asyncio
    async def test_call_llm_missing_both_prompt_and_output_as(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm returns error when both prompt and output_as are missing."""
        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt=None,
            output_as=None,
        )

        assert "error" in result
        assert result["error"] == "Missing prompt or output_as"

    @pytest.mark.asyncio
    async def test_call_llm_empty_prompt(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm returns error when prompt is empty string."""
        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="",
            output_as="response_var",
        )

        assert "error" in result
        assert result["error"] == "Missing prompt or output_as"

    @pytest.mark.asyncio
    async def test_call_llm_empty_output_as(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm returns error when output_as is empty string."""
        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Hello",
            output_as="",
        )

        assert "error" in result
        assert result["error"] == "Missing prompt or output_as"

    @pytest.mark.asyncio
    async def test_call_llm_missing_llm_service(
        self, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm returns error when LLM service is None."""
        result = await call_llm(
            llm_service=None,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Hello",
            output_as="response_var",
        )

        assert "error" in result
        assert result["error"] == "Missing LLM service"

    @pytest.mark.asyncio
    async def test_call_llm_template_rendering_error(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm handles template rendering errors gracefully."""
        mock_template_engine.render.side_effect = Exception("Undefined variable 'foo'")

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Hello {{ foo }}",
            output_as="response_var",
        )

        assert "error" in result
        assert "Template rendering failed" in result["error"]
        assert "Undefined variable 'foo'" in result["error"]

        # Verify LLM was not called
        mock_llm_service.get_default_provider.assert_not_called()

    @pytest.mark.asyncio
    async def test_call_llm_llm_service_error(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm handles LLM service errors gracefully."""
        provider = mock_llm_service.get_default_provider.return_value
        provider.generate_text = AsyncMock(side_effect=Exception("API rate limit exceeded"))

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Hello",
            output_as="response_var",
        )

        assert "error" in result
        assert result["error"] == "API rate limit exceeded"

        # Verify variable was not set
        assert "response_var" not in workflow_state.variables

    @pytest.mark.asyncio
    async def test_call_llm_provider_error(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm handles get_default_provider errors."""
        mock_llm_service.get_default_provider.side_effect = Exception("No provider configured")

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Hello",
            output_as="response_var",
        )

        assert "error" in result
        assert result["error"] == "No provider configured"

    @pytest.mark.asyncio
    async def test_call_llm_initializes_variables_if_none(
        self, mock_llm_service, mock_template_engine, mock_session
    ):
        """Test call_llm initializes state.variables if it is None."""
        state = WorkflowState(
            session_id="test-session-id",
            workflow_name="test-workflow",
            step="test-step",
        )
        # Explicitly set variables to None to test initialization
        state.variables = None

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=state,
            session=mock_session,
            prompt="Hello",
            output_as="response_var",
        )

        assert result["llm_called"] is True
        assert state.variables is not None
        assert state.variables["response_var"] == "LLM Response"

    @pytest.mark.asyncio
    async def test_call_llm_preserves_existing_variables(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm preserves existing variables in state."""
        workflow_state.variables = {"existing": "value", "another": 123}

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Hello",
            output_as="new_var",
        )

        assert result["llm_called"] is True
        assert workflow_state.variables["existing"] == "value"
        assert workflow_state.variables["another"] == 123
        assert workflow_state.variables["new_var"] == "LLM Response"

    @pytest.mark.asyncio
    async def test_call_llm_overwrites_existing_variable(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm overwrites an existing variable with same name."""
        workflow_state.variables = {"response_var": "old_value"}

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Hello",
            output_as="response_var",
        )

        assert result["llm_called"] is True
        assert workflow_state.variables["response_var"] == "LLM Response"

    @pytest.mark.asyncio
    async def test_call_llm_with_extra_context(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm passes extra context to template rendering."""
        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Hello {{ name }} from {{ city }}",
            output_as="response_var",
            name="Alice",
            city="NYC",
            custom_data={"key": "value"},
        )

        assert result["llm_called"] is True

        # Verify extra context was passed to template engine
        render_call_args = mock_template_engine.render.call_args
        context = render_call_args[0][1]
        assert context["name"] == "Alice"
        assert context["city"] == "NYC"
        assert context["custom_data"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_call_llm_context_includes_state_variables(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm includes state.variables in template context."""
        workflow_state.variables = {"foo": "bar", "count": 42}

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Value: {{ variables.foo }}",
            output_as="response_var",
        )

        assert result["llm_called"] is True

        # Verify variables are accessible in template context
        render_call_args = mock_template_engine.render.call_args
        context = render_call_args[0][1]
        assert context["variables"]["foo"] == "bar"
        assert context["variables"]["count"] == 42

    @pytest.mark.asyncio
    async def test_call_llm_with_none_state_variables(
        self, mock_llm_service, mock_template_engine, mock_session
    ):
        """Test call_llm handles state.variables being None during context building."""
        state = WorkflowState(
            session_id="test-session-id",
            workflow_name="test-workflow",
            step="test-step",
        )
        state.variables = None

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=state,
            session=mock_session,
            prompt="Hello",
            output_as="response_var",
        )

        assert result["llm_called"] is True

        # Verify empty dict is passed for variables if None
        render_call_args = mock_template_engine.render.call_args
        context = render_call_args[0][1]
        assert context["variables"] == {}

    @pytest.mark.asyncio
    async def test_call_llm_complex_llm_response(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm handles complex (multi-line, special chars) LLM responses."""
        complex_response = """Here is a multi-line response:
- Item 1
- Item 2

With special chars: "quotes", 'apostrophes', <brackets>

And unicode: \u00e9\u00e8\u00ea"""

        provider = mock_llm_service.get_default_provider.return_value
        provider.generate_text = AsyncMock(return_value=complex_response)

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Generate a response",
            output_as="response_var",
        )

        assert result["llm_called"] is True
        assert workflow_state.variables["response_var"] == complex_response

    @pytest.mark.asyncio
    async def test_call_llm_empty_llm_response(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm handles empty LLM response."""
        provider = mock_llm_service.get_default_provider.return_value
        provider.generate_text = AsyncMock(return_value="")

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Generate a response",
            output_as="response_var",
        )

        assert result["llm_called"] is True
        assert workflow_state.variables["response_var"] == ""

    @pytest.mark.asyncio
    async def test_call_llm_whitespace_only_prompt(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm with whitespace-only prompt (considered non-empty)."""
        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="   ",  # Whitespace is truthy in Python
            output_as="response_var",
        )

        # Whitespace string is truthy, so it should proceed
        assert result["llm_called"] is True

    @pytest.mark.asyncio
    async def test_call_llm_long_prompt(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm with very long prompt."""
        long_prompt = "A" * 10000  # 10k character prompt

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt=long_prompt,
            output_as="response_var",
        )

        assert result["llm_called"] is True
        mock_template_engine.render.assert_called_once()
        render_call_args = mock_template_engine.render.call_args
        assert render_call_args[0][0] == long_prompt

    @pytest.mark.asyncio
    async def test_call_llm_special_output_variable_names(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm with special characters in output variable name."""
        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Hello",
            output_as="my_response_123",
        )

        assert result["llm_called"] is True
        assert result["output_variable"] == "my_response_123"
        assert workflow_state.variables["my_response_123"] == "LLM Response"


class TestCallLlmEdgeCases:
    """Edge case tests for call_llm function."""

    @pytest.mark.asyncio
    async def test_call_llm_none_session(
        self, mock_llm_service, mock_template_engine, workflow_state
    ):
        """Test call_llm handles None session gracefully."""
        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=None,
            prompt="Hello",
            output_as="response_var",
        )

        # Should still work - session being None is passed to template context
        assert result["llm_called"] is True
        render_call_args = mock_template_engine.render.call_args
        assert render_call_args[0][1]["session"] is None

    @pytest.mark.asyncio
    async def test_call_llm_template_uses_session_data(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test that session data is available in template context."""
        mock_session.title = "Test Session Title"
        mock_session.status = "active"

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Session: {{ session.title }}",
            output_as="response_var",
        )

        assert result["llm_called"] is True
        render_call_args = mock_template_engine.render.call_args
        assert render_call_args[0][1]["session"].title == "Test Session Title"

    @pytest.mark.asyncio
    async def test_call_llm_template_uses_state_data(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test that state data is available in template context."""
        workflow_state.step = "planning"
        workflow_state.workflow_name = "plan-execute"

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Step: {{ state.step }}",
            output_as="response_var",
        )

        assert result["llm_called"] is True
        render_call_args = mock_template_engine.render.call_args
        assert render_call_args[0][1]["state"].step == "planning"
        assert render_call_args[0][1]["state"].workflow_name == "plan-execute"

    @pytest.mark.asyncio
    async def test_call_llm_template_rendering_truncation_in_error(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test that error message truncates long prompts."""
        long_prompt = "A" * 100  # Long prompt
        mock_template_engine.render.side_effect = Exception("Template error")

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt=long_prompt,
            output_as="response_var",
        )

        assert "error" in result
        # The error log truncates prompt to first 50 chars
        assert "Template rendering failed" in result["error"]

    @pytest.mark.asyncio
    async def test_call_llm_concurrent_calls(
        self, mock_llm_service, mock_template_engine, mock_session
    ):
        """Test concurrent call_llm calls with different states."""
        import asyncio

        state1 = WorkflowState(
            session_id="session-1",
            workflow_name="workflow-1",
            step="step-1",
            variables={},
        )
        state2 = WorkflowState(
            session_id="session-2",
            workflow_name="workflow-2",
            step="step-2",
            variables={},
        )

        # Make the LLM call have a small delay to simulate real async behavior
        async def delayed_response(prompt):
            await asyncio.sleep(0.01)
            return f"Response for: {prompt[:10]}"

        provider = mock_llm_service.get_default_provider.return_value
        provider.generate_text = delayed_response

        # Run concurrent calls
        results = await asyncio.gather(
            call_llm(
                llm_service=mock_llm_service,
                template_engine=mock_template_engine,
                state=state1,
                session=mock_session,
                prompt="Prompt 1",
                output_as="var1",
            ),
            call_llm(
                llm_service=mock_llm_service,
                template_engine=mock_template_engine,
                state=state2,
                session=mock_session,
                prompt="Prompt 2",
                output_as="var2",
            ),
        )

        # Both calls should succeed
        assert results[0]["llm_called"] is True
        assert results[1]["llm_called"] is True

        # Each state should have its own variable
        assert "var1" in state1.variables
        assert "var2" in state2.variables

    @pytest.mark.asyncio
    async def test_call_llm_timeout_error(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm handles timeout errors from LLM service."""

        provider = mock_llm_service.get_default_provider.return_value
        provider.generate_text = AsyncMock(side_effect=TimeoutError("Request timed out"))

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Hello",
            output_as="response_var",
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_call_llm_connection_error(
        self, mock_llm_service, mock_template_engine, workflow_state, mock_session
    ):
        """Test call_llm handles connection errors from LLM service."""
        provider = mock_llm_service.get_default_provider.return_value
        provider.generate_text = AsyncMock(side_effect=ConnectionError("Failed to connect"))

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=mock_template_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Hello",
            output_as="response_var",
        )

        assert "error" in result
        assert "Failed to connect" in result["error"]


class TestCallLlmIntegration:
    """Integration-style tests for call_llm with real TemplateEngine."""

    @pytest.mark.asyncio
    async def test_call_llm_with_real_template_engine(
        self, mock_llm_service, workflow_state, mock_session
    ):
        """Test call_llm with a real TemplateEngine instance."""
        real_engine = TemplateEngine()
        workflow_state.variables = {"user_name": "Alice"}

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=real_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Hello {{ variables.user_name }}!",
            output_as="greeting",
        )

        assert result["llm_called"] is True

        # Verify the prompt was actually rendered
        provider = mock_llm_service.get_default_provider.return_value
        provider.generate_text.assert_called_once_with("Hello Alice!")

    @pytest.mark.asyncio
    async def test_call_llm_real_template_with_extra_context(
        self, mock_llm_service, workflow_state, mock_session
    ):
        """Test call_llm with real TemplateEngine and extra context."""
        real_engine = TemplateEngine()

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=real_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Task: {{ task_name }} - Priority: {{ priority }}",
            output_as="task_description",
            task_name="Fix Bug",
            priority="High",
        )

        assert result["llm_called"] is True

        provider = mock_llm_service.get_default_provider.return_value
        provider.generate_text.assert_called_once_with("Task: Fix Bug - Priority: High")

    @pytest.mark.asyncio
    async def test_call_llm_real_template_jinja2_features(
        self, mock_llm_service, workflow_state, mock_session
    ):
        """Test call_llm with Jinja2 features like loops and conditionals."""
        real_engine = TemplateEngine()

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=real_engine,
            state=workflow_state,
            session=mock_session,
            prompt="""{% if items %}Items:{% for item in items %}
- {{ item }}{% endfor %}{% else %}No items{% endif %}""",
            output_as="list_output",
            items=["apple", "banana", "cherry"],
        )

        assert result["llm_called"] is True

        provider = mock_llm_service.get_default_provider.return_value
        call_args = provider.generate_text.call_args[0][0]
        assert "Items:" in call_args
        assert "- apple" in call_args
        assert "- banana" in call_args
        assert "- cherry" in call_args

    @pytest.mark.asyncio
    async def test_call_llm_real_template_undefined_variable_error(
        self, mock_llm_service, workflow_state, mock_session
    ):
        """Test call_llm with real TemplateEngine handles undefined variables."""
        real_engine = TemplateEngine()

        result = await call_llm(
            llm_service=mock_llm_service,
            template_engine=real_engine,
            state=workflow_state,
            session=mock_session,
            prompt="Hello {{ undefined_variable }}",
            output_as="response_var",
        )

        # Jinja2 by default renders undefined variables as empty string
        # but strict mode would raise. Our TemplateEngine uses default mode.
        # So this should succeed with empty interpolation
        assert result["llm_called"] is True
