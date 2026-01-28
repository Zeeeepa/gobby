"""Integration tests for context injection flow in agents."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.agents.context import ContextResolver, format_injected_prompt
from gobby.mcp_proxy.tools.agents import create_agents_registry


@pytest.fixture
def mock_runner():
    """Create a mock agent runner."""
    runner = MagicMock()
    runner.can_spawn.return_value = (True, "OK", 0)
    return runner


@pytest.fixture
def mock_session_manager():
    """Create a mock session manager with a parent session."""
    manager = MagicMock()
    parent = MagicMock()
    parent.id = "sess-parent"
    parent.summary_markdown = "# Parent Summary\n\nThis is context."
    parent.compact_markdown = "## Handoff\n\nCompact context here."
    manager.get.return_value = parent
    return manager


@pytest.fixture
def mock_message_manager():
    """Create a mock message manager."""
    manager = MagicMock()
    manager.get_messages = AsyncMock(
        return_value=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
    )
    return manager


@pytest.fixture
def temp_project():
    """Create a temporary project directory with a context file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a context file
        context_file = Path(tmpdir) / "context.md"
        context_file.write_text("# File Context\n\nContent from file.")
        yield Path(tmpdir)


@pytest.mark.integration
class TestContextResolverIntegration:
    """Integration tests for ContextResolver with all source types."""

    async def test_resolves_summary_markdown(self, mock_session_manager, mock_message_manager):
        """Resolves summary_markdown from parent session."""
        resolver = ContextResolver(
            session_manager=mock_session_manager,
            message_manager=mock_message_manager,
        )

        result = await resolver.resolve("summary_markdown", "sess-parent")

        assert "Parent Summary" in result
        assert "This is context" in result

    async def test_resolves_compact_markdown(self, mock_session_manager, mock_message_manager):
        """Resolves compact_markdown from parent session."""
        resolver = ContextResolver(
            session_manager=mock_session_manager,
            message_manager=mock_message_manager,
        )

        result = await resolver.resolve("compact_markdown", "sess-parent")

        assert "Handoff" in result
        assert "Compact context" in result

    async def test_resolves_transcript(self, mock_session_manager, mock_message_manager):
        """Resolves transcript from parent session."""
        resolver = ContextResolver(
            session_manager=mock_session_manager,
            message_manager=mock_message_manager,
        )

        result = await resolver.resolve("transcript:5", "sess-parent")

        assert "**user**: Hello" in result
        assert "**assistant**: Hi there!" in result

    async def test_resolves_file(self, mock_session_manager, mock_message_manager, temp_project):
        """Resolves file content from project."""
        resolver = ContextResolver(
            session_manager=mock_session_manager,
            message_manager=mock_message_manager,
            project_path=temp_project,
        )

        result = await resolver.resolve("file:context.md", "sess-parent")

        assert "File Context" in result
        assert "Content from file" in result

    async def test_resolves_session_id(self, mock_session_manager, mock_message_manager):
        """Resolves summary from specific session by ID."""
        resolver = ContextResolver(
            session_manager=mock_session_manager,
            message_manager=mock_message_manager,
        )

        await resolver.resolve("session_id:sess-target", "sess-parent")

        # Should call get() with the target session ID
        mock_session_manager.get.assert_called_with("sess-target")


@pytest.mark.integration
class TestFormatInjectedPromptIntegration:
    """Integration tests for prompt injection formatting."""

    def test_formats_context_with_prompt(self):
        """Context is properly formatted with prompt."""
        context = "# Summary\n\nImportant context."
        prompt = "Do the task"

        result = format_injected_prompt(context, prompt)

        assert "## Context from Parent Session" in result
        assert "Important context" in result
        assert "## Task" in result
        assert "Do the task" in result

    def test_preserves_prompt_when_no_context(self):
        """Returns original prompt when context is empty."""
        result = format_injected_prompt("", "Do the task")

        assert result == "Do the task"
        assert "Context" not in result


@pytest.mark.integration
class TestAgentsRegistryContextIntegration:
    """Integration tests for agents registry creation."""

    def test_registry_creates_with_runner(self, mock_runner):
        """Registry is created with just a runner."""
        registry = create_agents_registry(runner=mock_runner)

        assert registry.name == "gobby-agents"
        # Registry should have spawn_agent tool (unified tool)
        tools = registry.list_tools()
        tool_names = [t["name"] for t in tools]
        assert "spawn_agent" in tool_names


@pytest.mark.integration
class TestErrorHandling:
    """Tests for error handling in context injection flow."""

    async def test_handles_missing_session(self, mock_session_manager, mock_message_manager):
        """Handles missing session gracefully."""
        mock_session_manager.get.return_value = None

        resolver = ContextResolver(
            session_manager=mock_session_manager,
            message_manager=mock_message_manager,
        )

        from gobby.agents.context import ContextResolutionError

        with pytest.raises(ContextResolutionError) as exc_info:
            await resolver.resolve("summary_markdown", "sess-nonexistent")

        assert "Session not found" in str(exc_info.value)

    async def test_handles_invalid_source_format(self, mock_session_manager, mock_message_manager):
        """Handles invalid source format gracefully."""
        resolver = ContextResolver(
            session_manager=mock_session_manager,
            message_manager=mock_message_manager,
        )

        from gobby.agents.context import ContextResolutionError

        with pytest.raises(ContextResolutionError) as exc_info:
            await resolver.resolve("invalid_source", "sess-parent")

        assert "Unknown context source format" in str(exc_info.value)

    async def test_handles_file_not_found(
        self, mock_session_manager, mock_message_manager, temp_project
    ):
        """Handles missing file gracefully."""
        resolver = ContextResolver(
            session_manager=mock_session_manager,
            message_manager=mock_message_manager,
            project_path=temp_project,
        )

        from gobby.agents.context import ContextResolutionError

        with pytest.raises(ContextResolutionError) as exc_info:
            await resolver.resolve("file:nonexistent.md", "sess-parent")

        assert "File not found" in str(exc_info.value)
