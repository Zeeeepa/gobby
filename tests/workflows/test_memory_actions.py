from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.memory.manager import MemoryManager
from gobby.workflows.actions import ActionContext, ActionExecutor
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.memory_actions import (
    memory_recall_relevant,
    memory_save,
    memory_sync_export,
    memory_sync_import,
    reset_memory_injection_tracking,
)
from gobby.workflows.templates import TemplateEngine

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_mem_services():
    services = {
        "template_engine": MagicMock(spec=TemplateEngine),
        "llm_service": AsyncMock(),
        "transcript_processor": MagicMock(),
        "config": MagicMock(),
        "tool_proxy_getter": AsyncMock(),
        "memory_manager": MagicMock(spec=MemoryManager),
        "memory_sync_manager": AsyncMock(),
    }
    # Manually attach config mocks because spec might strict on attributes not in class __init__
    services["memory_manager"].config = MagicMock()
    services["memory_manager"].config.enabled = True
    return services


@pytest.fixture
def mem_action_executor(temp_db, session_manager, mock_mem_services):
    executor = ActionExecutor(
        temp_db,
        session_manager,
        mock_mem_services["template_engine"],
        llm_service=mock_mem_services["llm_service"],
        transcript_processor=mock_mem_services["transcript_processor"],
        config=mock_mem_services["config"],
        tool_proxy_getter=mock_mem_services["tool_proxy_getter"],
        memory_manager=mock_mem_services["memory_manager"],
        memory_sync_manager=mock_mem_services["memory_sync_manager"],
    )
    # Ensure handlers are registered
    return executor


@pytest.fixture
def mem_workflow_state():
    return WorkflowState(
        session_id="test-session-id", workflow_name="test-workflow", step="test-step"
    )


@pytest.fixture
def mem_action_context(temp_db, session_manager, mem_workflow_state, mock_mem_services):
    return ActionContext(
        session_id=mem_workflow_state.session_id,
        state=mem_workflow_state,
        db=temp_db,
        session_manager=session_manager,
        template_engine=MagicMock(spec=TemplateEngine),
        llm_service=mock_mem_services["llm_service"],
        tool_proxy_getter=mock_mem_services["tool_proxy_getter"],
        memory_manager=mock_mem_services["memory_manager"],
        memory_sync_manager=mock_mem_services["memory_sync_manager"],
    )


@pytest.mark.asyncio
async def test_memory_sync_import(mem_action_executor, mem_action_context, mock_mem_services):
    # Since memories and skills are decoupled, import_from_files returns an int count
    mock_mem_services["memory_sync_manager"].import_from_files.return_value = 10

    result = await mem_action_executor.execute("memory_sync_import", mem_action_context)

    assert result is not None
    assert result["imported"] == {"memories": 10}
    mock_mem_services["memory_sync_manager"].import_from_files.assert_called_once()


@pytest.mark.asyncio
async def test_memory_sync_export(mem_action_executor, mem_action_context, mock_mem_services):
    # Since memories and skills are decoupled, export_to_files returns an int count
    mock_mem_services["memory_sync_manager"].export_to_files.return_value = 10

    result = await mem_action_executor.execute("memory_sync_export", mem_action_context)

    assert result is not None
    assert result["exported"] == {"memories": 10}
    mock_mem_services["memory_sync_manager"].export_to_files.assert_called_once()


# --- Selective Injection Tests ---


@pytest.mark.asyncio
async def test_memory_save_creates_memory(
    mem_action_executor, mem_action_context, session_manager, sample_project, mock_mem_services
):
    """Test memory_save creates a memory with specified parameters."""
    session = session_manager.register(
        external_id="save-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    mem_action_context.session_id = session.id
    mem_action_context.state.session_id = session.id

    mock_mem_services["memory_manager"].config.enabled = True
    mock_mem_services["memory_manager"].content_exists.return_value = False

    mock_memory = MagicMock()
    mock_memory.id = "mem-123"
    mock_mem_services["memory_manager"].remember.return_value = mock_memory

    result = await mem_action_executor.execute(
        "memory_save",
        mem_action_context,
        content="User prefers dark mode",
        memory_type="preference",
        importance=0.8,
        tags=["ui", "settings"],
    )

    assert result is not None
    assert result["saved"] is True
    assert result["memory_id"] == "mem-123"
    assert result["memory_type"] == "preference"
    assert result["importance"] == 0.8

    mock_mem_services["memory_manager"].remember.assert_called_once_with(
        content="User prefers dark mode",
        memory_type="preference",
        importance=0.8,
        project_id=sample_project["id"],
        source_type="workflow",
        source_session_id=session.id,
        tags=["ui", "settings"],
    )


@pytest.mark.asyncio
async def test_memory_save_requires_content(
    mem_action_executor, mem_action_context, mock_mem_services
):
    """Test memory_save fails without content parameter."""
    mock_mem_services["memory_manager"].config.enabled = True

    result = await mem_action_executor.execute("memory_save", mem_action_context)

    assert result is not None
    assert "error" in result
    assert "content" in result["error"]


@pytest.mark.asyncio
async def test_memory_save_skips_duplicates(
    mem_action_executor, mem_action_context, session_manager, sample_project, mock_mem_services
):
    """Test memory_save skips duplicate content."""
    session = session_manager.register(
        external_id="dup-save-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    mem_action_context.session_id = session.id
    mem_action_context.state.session_id = session.id

    mock_mem_services["memory_manager"].config.enabled = True
    mock_mem_services["memory_manager"].content_exists.return_value = True

    result = await mem_action_executor.execute(
        "memory_save",
        mem_action_context,
        content="Already exists",
    )

    assert result is not None
    assert result["saved"] is False
    assert result["reason"] == "duplicate"
    mock_mem_services["memory_manager"].remember.assert_not_called()


@pytest.mark.asyncio
async def test_memory_save_uses_defaults(
    mem_action_executor, mem_action_context, session_manager, sample_project, mock_mem_services
):
    """Test memory_save uses default values for optional parameters."""
    session = session_manager.register(
        external_id="default-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    mem_action_context.session_id = session.id
    mem_action_context.state.session_id = session.id

    mock_mem_services["memory_manager"].config.enabled = True
    mock_mem_services["memory_manager"].content_exists.return_value = False

    mock_memory = MagicMock()
    mock_memory.id = "mem-456"
    mock_mem_services["memory_manager"].remember.return_value = mock_memory

    result = await mem_action_executor.execute(
        "memory_save",
        mem_action_context,
        content="Simple fact",
    )

    assert result is not None
    assert result["saved"] is True
    assert result["memory_type"] == "fact"
    assert result["importance"] == 0.5

    # Verify defaults were used
    call_kwargs = mock_mem_services["memory_manager"].remember.call_args[1]
    assert call_kwargs["memory_type"] == "fact"
    assert call_kwargs["importance"] == 0.5
    assert call_kwargs["tags"] == []


# --- memory_recall_relevant Action Tests ---


@pytest.mark.asyncio
async def test_memory_recall_relevant_with_prompt(
    mem_action_executor, mem_action_context, session_manager, sample_project, mock_mem_services
):
    """Test memory_recall_relevant searches based on prompt_text."""
    session = session_manager.register(
        external_id="recall-rel-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    mem_action_context.session_id = session.id
    mem_action_context.state.session_id = session.id
    mem_action_context.event_data = {"prompt_text": "How do I write tests for this project?"}

    mock_mem_services["memory_manager"].config.enabled = True

    m1 = MagicMock(memory_type="fact", content="Tests are in tests/ directory")
    m2 = MagicMock(memory_type="fact", content="Use pytest for testing")
    mock_mem_services["memory_manager"].recall.return_value = [m1, m2]

    result = await mem_action_executor.execute("memory_recall_relevant", mem_action_context)

    assert result is not None
    assert result["injected"] is True
    assert result["count"] == 2
    assert "inject_context" in result

    # Verify semantic search was used
    mock_mem_services["memory_manager"].recall.assert_called_once()
    call_kwargs = mock_mem_services["memory_manager"].recall.call_args[1]
    assert call_kwargs["query"] == "How do I write tests for this project?"
    assert call_kwargs["search_mode"] == "auto"


@pytest.mark.asyncio
async def test_memory_recall_relevant_no_prompt(
    mem_action_executor, mem_action_context, mock_mem_services
):
    """Test memory_recall_relevant returns None when no prompt_text."""
    mock_mem_services["memory_manager"].config.enabled = True
    mem_action_context.event_data = None  # No event data

    result = await mem_action_executor.execute("memory_recall_relevant", mem_action_context)

    assert result is None
    mock_mem_services["memory_manager"].recall.assert_not_called()


@pytest.mark.asyncio
async def test_memory_recall_relevant_skips_commands(
    mem_action_executor, mem_action_context, mock_mem_services
):
    """Test memory_recall_relevant skips slash commands."""
    mock_mem_services["memory_manager"].config.enabled = True
    mem_action_context.event_data = {"prompt_text": "/clear"}

    result = await mem_action_executor.execute("memory_recall_relevant", mem_action_context)

    assert result is None
    mock_mem_services["memory_manager"].recall.assert_not_called()


@pytest.mark.asyncio
async def test_memory_recall_relevant_skips_short_prompts(
    mem_action_executor, mem_action_context, mock_mem_services
):
    """Test memory_recall_relevant skips very short prompts."""
    mock_mem_services["memory_manager"].config.enabled = True
    mem_action_context.event_data = {"prompt_text": "hi there"}

    result = await mem_action_executor.execute("memory_recall_relevant", mem_action_context)

    assert result is None
    mock_mem_services["memory_manager"].recall.assert_not_called()


@pytest.mark.asyncio
async def test_memory_recall_relevant_no_memories_found(
    mem_action_executor, mem_action_context, session_manager, sample_project, mock_mem_services
):
    """Test memory_recall_relevant returns empty when no relevant memories."""
    session = session_manager.register(
        external_id="recall-empty-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    mem_action_context.session_id = session.id
    mem_action_context.state.session_id = session.id
    mem_action_context.event_data = {"prompt_text": "What is the meaning of life?"}

    mock_mem_services["memory_manager"].config.enabled = True
    mock_mem_services["memory_manager"].recall.return_value = []

    result = await mem_action_executor.execute("memory_recall_relevant", mem_action_context)

    assert result is not None
    assert result["injected"] is False
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_memory_recall_relevant_respects_kwargs(
    mem_action_executor, mem_action_context, session_manager, sample_project, mock_mem_services
):
    """Test memory_recall_relevant uses limit and min_importance kwargs."""
    session = session_manager.register(
        external_id="recall-kwargs-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    mem_action_context.session_id = session.id
    mem_action_context.state.session_id = session.id
    mem_action_context.event_data = {"prompt_text": "Tell me about the database schema"}

    mock_mem_services["memory_manager"].config.enabled = True

    m1 = MagicMock(memory_type="fact", content="Database uses SQLite")
    mock_mem_services["memory_manager"].recall.return_value = [m1]

    result = await mem_action_executor.execute(
        "memory_recall_relevant",
        mem_action_context,
        limit=3,
        min_importance=0.7,
    )

    assert result is not None
    assert result["injected"] is True

    # Verify kwargs were passed
    call_kwargs = mock_mem_services["memory_manager"].recall.call_args[1]
    assert call_kwargs["limit"] == 3
    assert call_kwargs["min_importance"] == 0.7


# =============================================================================
# DIRECT FUNCTION TESTS - Testing memory_actions.py functions directly
# These tests bypass ActionExecutor to directly test the functions
# =============================================================================


class TestMemorySyncImportDirect:
    """Direct tests for memory_sync_import function."""

    @pytest.mark.asyncio
    async def test_memory_sync_import_no_manager(self):
        """Test memory_sync_import returns error when manager is None."""
        result = await memory_sync_import(None)
        assert result == {"error": "Memory Sync Manager not available"}

    @pytest.mark.asyncio
    async def test_memory_sync_import_success(self):
        """Test memory_sync_import success path."""
        mock_manager = AsyncMock()
        mock_manager.import_from_files.return_value = 5

        result = await memory_sync_import(mock_manager)

        assert result == {"imported": {"memories": 5}}
        mock_manager.import_from_files.assert_awaited_once()


class TestMemorySyncExportDirect:
    """Direct tests for memory_sync_export function."""

    @pytest.mark.asyncio
    async def test_memory_sync_export_no_manager(self):
        """Test memory_sync_export returns error when manager is None."""
        result = await memory_sync_export(None)
        assert result == {"error": "Memory Sync Manager not available"}

    @pytest.mark.asyncio
    async def test_memory_sync_export_success(self):
        """Test memory_sync_export success path."""
        mock_manager = AsyncMock()
        mock_manager.export_to_files.return_value = 7

        result = await memory_sync_export(mock_manager)

        assert result == {"exported": {"memories": 7}}
        mock_manager.export_to_files.assert_awaited_once()


class TestMemorySaveDirect:
    """Direct tests for memory_save function."""

    @pytest.mark.asyncio
    async def test_memory_save_no_memory_manager(self):
        """Test memory_save returns error when memory_manager is None."""
        result = await memory_save(
            memory_manager=None,
            session_manager=MagicMock(),
            session_id="test-session",
            content="test content",
        )
        assert result == {"error": "Memory Manager not available"}

    @pytest.mark.asyncio
    async def test_memory_save_config_disabled(self):
        """Test memory_save returns None when config.enabled is False."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = False

        result = await memory_save(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            content="test content",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_memory_save_no_project_id(self):
        """Test memory_save returns error when no project_id found."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True

        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.project_id = None
        mock_session_manager.get.return_value = mock_session

        result = await memory_save(
            memory_manager=mock_memory_manager,
            session_manager=mock_session_manager,
            session_id="test-session",
            content="test content",
        )
        assert result == {"error": "No project_id found"}

    @pytest.mark.asyncio
    async def test_memory_save_session_not_found_no_project(self):
        """Test memory_save returns error when session not found and no project_id."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True

        mock_session_manager = MagicMock()
        mock_session_manager.get.return_value = None

        result = await memory_save(
            memory_manager=mock_memory_manager,
            session_manager=mock_session_manager,
            session_id="test-session",
            content="test content",
        )
        assert result == {"error": "No project_id found"}

    @pytest.mark.asyncio
    async def test_memory_save_normalizes_invalid_memory_type(self):
        """Test memory_save normalizes invalid memory_type to 'fact'."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.content_exists.return_value = False
        mock_memory_manager.remember = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem-123"
        mock_memory_manager.remember.return_value = mock_memory

        result = await memory_save(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            content="test content",
            memory_type="invalid_type",
            project_id="proj-123",
        )

        assert result is not None
        assert result["saved"] is True
        assert result["memory_type"] == "fact"

    @pytest.mark.asyncio
    async def test_memory_save_normalizes_invalid_importance(self):
        """Test memory_save normalizes invalid importance to 0.5."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.content_exists.return_value = False
        mock_memory_manager.remember = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem-123"
        mock_memory_manager.remember.return_value = mock_memory

        result = await memory_save(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            content="test content",
            importance="not a number",
            project_id="proj-123",
        )

        assert result is not None
        assert result["saved"] is True
        assert result["importance"] == 0.5

    @pytest.mark.asyncio
    async def test_memory_save_clamps_importance(self):
        """Test memory_save clamps importance to valid range."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.content_exists.return_value = False
        mock_memory_manager.remember = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem-123"
        mock_memory_manager.remember.return_value = mock_memory

        # Test clamping high value
        result = await memory_save(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            content="test content",
            importance=2.0,
            project_id="proj-123",
        )

        assert result is not None
        assert result["importance"] == 1.0

    @pytest.mark.asyncio
    async def test_memory_save_normalizes_invalid_tags(self):
        """Test memory_save normalizes invalid tags to empty list."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.content_exists.return_value = False
        mock_memory_manager.remember = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem-123"
        mock_memory_manager.remember.return_value = mock_memory

        result = await memory_save(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            content="test content",
            tags="not a list",
            project_id="proj-123",
        )

        assert result is not None
        assert result["saved"] is True
        call_kwargs = mock_memory_manager.remember.call_args[1]
        assert call_kwargs["tags"] == []

    @pytest.mark.asyncio
    async def test_memory_save_exception_handling(self):
        """Test memory_save handles exceptions gracefully."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.content_exists.return_value = False
        mock_memory_manager.remember = AsyncMock(side_effect=Exception("DB error"))

        result = await memory_save(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            content="test content",
            project_id="proj-123",
        )

        assert result is not None
        assert "error" in result
        assert "DB error" in result["error"]


class TestMemoryRecallRelevantDirect:
    """Direct tests for memory_recall_relevant function."""

    @pytest.mark.asyncio
    async def test_memory_recall_relevant_no_memory_manager(self):
        """Test memory_recall_relevant returns None when memory_manager is None."""
        result = await memory_recall_relevant(
            memory_manager=None,
            session_manager=MagicMock(),
            session_id="test-session",
            prompt_text="test prompt",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_memory_recall_relevant_config_disabled(self):
        """Test memory_recall_relevant returns None when config.enabled is False."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = False

        result = await memory_recall_relevant(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            prompt_text="test prompt",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_memory_recall_relevant_no_prompt_text(self):
        """Test memory_recall_relevant returns None when prompt_text is None."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True

        result = await memory_recall_relevant(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            prompt_text=None,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_memory_recall_relevant_resolves_project_from_session(self):
        """Test memory_recall_relevant resolves project_id from session."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True

        m1 = MagicMock()
        m1.memory_type = "fact"
        m1.content = "Test memory"
        mock_memory_manager.recall.return_value = [m1]

        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.project_id = "proj-from-session"
        mock_session_manager.get.return_value = mock_session

        result = await memory_recall_relevant(
            memory_manager=mock_memory_manager,
            session_manager=mock_session_manager,
            session_id="test-session",
            prompt_text="a longer prompt text here",
        )

        assert result is not None
        call_kwargs = mock_memory_manager.recall.call_args[1]
        assert call_kwargs["project_id"] == "proj-from-session"

    @pytest.mark.asyncio
    async def test_memory_recall_relevant_exception_handling(self):
        """Test memory_recall_relevant handles exceptions gracefully."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.recall.side_effect = Exception("Search error")

        result = await memory_recall_relevant(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            prompt_text="a longer prompt text here",
            project_id="proj-123",
        )

        assert result is not None
        assert "error" in result
        assert "Search error" in result["error"]


# Additional edge case tests for improved coverage


class TestMemoryRecallRelevantEdgeCases:
    """Additional edge case tests for memory_recall_relevant."""

    @pytest.mark.asyncio
    async def test_memory_recall_relevant_session_not_found_uses_none_project(self):
        """Test memory_recall_relevant when session not found and no explicit project_id."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True

        mock_session_manager = MagicMock()
        mock_session_manager.get.return_value = None  # Session not found

        m1 = MagicMock()
        m1.memory_type = "fact"
        m1.content = "Test memory"
        mock_memory_manager.recall.return_value = [m1]

        result = await memory_recall_relevant(
            memory_manager=mock_memory_manager,
            session_manager=mock_session_manager,
            session_id="test-session",
            prompt_text="a longer prompt text here",
            project_id=None,  # No explicit project_id
        )

        assert result is not None
        # Verify recall was called with None project_id
        call_kwargs = mock_memory_manager.recall.call_args[1]
        assert call_kwargs["project_id"] is None


# =============================================================================
# MEMORY DEDUPLICATION TESTS
# =============================================================================


class TestMemoryDeduplication:
    """Tests for memory injection deduplication per session."""

    @pytest.mark.asyncio
    async def test_memory_recall_tracks_injected_ids_in_state(self):
        """Test that memory_recall_relevant tracks injected memory IDs in state."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True

        m1 = MagicMock()
        m1.id = "mem-001"
        m1.memory_type = "fact"
        m1.content = "Test memory 1"
        m2 = MagicMock()
        m2.id = "mem-002"
        m2.memory_type = "fact"
        m2.content = "Test memory 2"
        mock_memory_manager.recall.return_value = [m1, m2]

        state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
        )

        result = await memory_recall_relevant(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            prompt_text="a longer prompt text here",
            project_id="proj-123",
            state=state,
        )

        assert result is not None
        assert result["injected"] is True
        assert result["count"] == 2

        # Verify IDs were tracked in state
        assert "_injected_memory_ids" in state.variables
        assert set(state.variables["_injected_memory_ids"]) == {"mem-001", "mem-002"}

    @pytest.mark.asyncio
    async def test_memory_recall_deduplicates_on_second_call(self):
        """Test that second call with same memories returns empty."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True

        m1 = MagicMock()
        m1.id = "mem-001"
        m1.memory_type = "fact"
        m1.content = "Test memory"
        mock_memory_manager.recall.return_value = [m1]

        state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
        )

        # First call
        result1 = await memory_recall_relevant(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            prompt_text="first prompt text here",
            project_id="proj-123",
            state=state,
        )

        assert result1 is not None
        assert result1["injected"] is True
        assert result1["count"] == 1

        # Second call with same memory
        result2 = await memory_recall_relevant(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            prompt_text="second prompt text here",
            project_id="proj-123",
            state=state,
        )

        assert result2 is not None
        assert result2["injected"] is False
        assert result2["count"] == 0
        assert result2.get("skipped") == 1

    @pytest.mark.asyncio
    async def test_memory_recall_allows_new_memories_after_first_call(self):
        """Test that new memories are still injected on subsequent calls."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True

        m1 = MagicMock()
        m1.id = "mem-001"
        m1.memory_type = "fact"
        m1.content = "Test memory 1"

        m2 = MagicMock()
        m2.id = "mem-002"
        m2.memory_type = "fact"
        m2.content = "Test memory 2"

        state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
        )

        # First call - returns m1
        mock_memory_manager.recall.return_value = [m1]
        result1 = await memory_recall_relevant(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            prompt_text="first prompt text here",
            project_id="proj-123",
            state=state,
        )

        assert result1["count"] == 1

        # Second call - returns m1 and m2, but only m2 is new
        mock_memory_manager.recall.return_value = [m1, m2]
        result2 = await memory_recall_relevant(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            prompt_text="second prompt text here",
            project_id="proj-123",
            state=state,
        )

        assert result2 is not None
        assert result2["injected"] is True
        assert result2["count"] == 1  # Only m2 is new

        # Verify both IDs are now tracked
        assert set(state.variables["_injected_memory_ids"]) == {"mem-001", "mem-002"}

    @pytest.mark.asyncio
    async def test_memory_recall_works_without_state(self):
        """Test that memory_recall_relevant works when state is None (no dedup)."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True

        m1 = MagicMock()
        m1.id = "mem-001"
        m1.memory_type = "fact"
        m1.content = "Test memory"
        mock_memory_manager.recall.return_value = [m1]

        # Call without state - should work without deduplication
        result = await memory_recall_relevant(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            prompt_text="prompt text here for test",
            project_id="proj-123",
            state=None,
        )

        assert result is not None
        assert result["injected"] is True
        assert result["count"] == 1


class TestResetMemoryInjectionTracking:
    """Tests for reset_memory_injection_tracking function."""

    def test_reset_clears_injected_ids(self) -> None:
        """Test that reset clears the injected memory IDs."""
        state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
        )
        state.variables = {"_injected_memory_ids": ["mem-001", "mem-002", "mem-003"]}

        result = reset_memory_injection_tracking(state=state)

        assert result["success"] is True
        assert result["cleared"] == 3
        assert state.variables["_injected_memory_ids"] == []

    def test_reset_returns_zero_when_no_ids(self) -> None:
        """Test that reset returns 0 cleared when no IDs exist."""
        state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
        )
        state.variables = {}

        result = reset_memory_injection_tracking(state=state)

        assert result["success"] is True
        assert result["cleared"] == 0

    def test_reset_handles_none_state(self) -> None:
        """Test that reset handles None state gracefully."""
        result = reset_memory_injection_tracking(state=None)

        assert result["success"] is False
        assert result["cleared"] == 0
        assert result["reason"] == "no_state"

    def test_reset_handles_state_without_variables(self) -> None:
        """Test that reset handles state without variables attribute."""
        state = MagicMock()
        state.variables = None

        result = reset_memory_injection_tracking(state=state)

        assert result["success"] is True
        assert result["cleared"] == 0

    @pytest.mark.asyncio
    async def test_reset_allows_reinjection(self):
        """Test that after reset, memories can be injected again."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True

        m1 = MagicMock()
        m1.id = "mem-001"
        m1.memory_type = "fact"
        m1.content = "Test memory"
        mock_memory_manager.recall.return_value = [m1]

        state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
        )

        # First call - memory is injected
        result1 = await memory_recall_relevant(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            prompt_text="first prompt text here",
            project_id="proj-123",
            state=state,
        )
        assert result1["count"] == 1

        # Second call - memory is deduplicated
        result2 = await memory_recall_relevant(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            prompt_text="second prompt text here",
            project_id="proj-123",
            state=state,
        )
        assert result2["count"] == 0
        assert result2.get("skipped") == 1

        # Reset tracking
        reset_result = reset_memory_injection_tracking(state=state)
        assert reset_result["cleared"] == 1

        # Third call - memory is injected again
        result3 = await memory_recall_relevant(
            memory_manager=mock_memory_manager,
            session_manager=MagicMock(),
            session_id="test-session",
            prompt_text="third prompt text here",
            project_id="proj-123",
            state=state,
        )
        assert result3["count"] == 1
        assert result3["injected"] is True
