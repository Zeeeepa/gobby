from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.memory.manager import MemoryManager
from gobby.workflows.actions import ActionContext, ActionExecutor
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.memory_actions import (
    _content_fingerprint,
    memory_extract,
    memory_recall_relevant,
    memory_save,
    memory_sync_export,
    memory_sync_import,
)
from gobby.workflows.templates import TemplateEngine


@pytest.fixture
def mock_mem_services():
    services = {
        "template_engine": MagicMock(spec=TemplateEngine),
        "llm_service": AsyncMock(),
        "transcript_processor": MagicMock(),
        "config": MagicMock(),
        "mcp_manager": AsyncMock(),
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
        mcp_manager=mock_mem_services["mcp_manager"],
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
        mcp_manager=mock_mem_services["mcp_manager"],
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


@pytest.mark.asyncio
async def test_memory_extract_from_summary(
    mem_action_executor, mem_action_context, session_manager, sample_project, mock_mem_services
):
    """Test memory extraction from session summary."""
    # Setup session with summary
    session = session_manager.register(
        external_id="extract-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    # Add summary to session
    session_manager.update_summary(
        session.id, summary_markdown="User prefers pytest. Project uses Python 3.11."
    )

    mem_action_context.session_id = session.id
    mem_action_context.state.session_id = session.id

    # Setup mocks
    mock_mem_services["memory_manager"].config.enabled = True
    mock_mem_services["memory_manager"].config.auto_extract = True
    mock_mem_services["memory_manager"].config.extraction_prompt = "Extract: {summary}"
    mock_mem_services["memory_manager"].content_exists.return_value = False

    # Mock LLM response - use MagicMock for sync method, AsyncMock for async generate_text
    mock_provider = MagicMock()
    mock_provider.generate_text = AsyncMock(
        return_value="""[
        {"content": "User prefers pytest", "memory_type": "preference", "importance": 0.7},
        {"content": "Project uses Python 3.11", "memory_type": "fact", "importance": 0.6}
    ]"""
    )
    # get_provider_for_feature is sync, so use MagicMock
    mock_llm_service = MagicMock()
    mock_llm_service.get_provider_for_feature.return_value = (mock_provider, "test-model", {})

    # Update context with sync mock
    mem_action_context.llm_service = mock_llm_service

    result = await mem_action_executor.execute("memory_extract", mem_action_context)

    assert result is not None
    assert result["extracted"] == 2
    assert mock_mem_services["memory_manager"].remember.call_count == 2


@pytest.mark.asyncio
async def test_memory_extract_no_summary(
    mem_action_executor, mem_action_context, session_manager, sample_project, mock_mem_services
):
    """Test memory extraction skips when no summary available."""
    session = session_manager.register(
        external_id="no-summary-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    # No summary set

    mem_action_context.session_id = session.id
    mem_action_context.state.session_id = session.id
    mem_action_context.llm_service = mock_mem_services["llm_service"]

    mock_mem_services["memory_manager"].config.enabled = True
    mock_mem_services["memory_manager"].config.auto_extract = True

    result = await mem_action_executor.execute("memory_extract", mem_action_context)

    assert result is not None
    assert result["extracted"] == 0
    assert result["reason"] == "no_summary"


@pytest.mark.asyncio
async def test_memory_extract_skips_duplicates(
    mem_action_executor, mem_action_context, session_manager, sample_project, mock_mem_services
):
    """Test memory extraction skips duplicate content."""
    session = session_manager.register(
        external_id="dup-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    session_manager.update_summary(session.id, summary_markdown="Some session content")

    mem_action_context.session_id = session.id
    mem_action_context.state.session_id = session.id
    mem_action_context.llm_service = mock_mem_services["llm_service"]

    mock_mem_services["memory_manager"].config.enabled = True
    mock_mem_services["memory_manager"].config.auto_extract = True
    mock_mem_services["memory_manager"].config.extraction_prompt = "Extract: {summary}"
    # First memory exists, second doesn't
    mock_mem_services["memory_manager"].content_exists.side_effect = [True, False]

    mock_provider = MagicMock()
    mock_provider.generate_text = AsyncMock(
        return_value="""[
        {"content": "Existing memory", "memory_type": "fact", "importance": 0.5},
        {"content": "New memory", "memory_type": "fact", "importance": 0.5}
    ]"""
    )
    mock_llm_service = MagicMock()
    mock_llm_service.get_provider_for_feature.return_value = (mock_provider, "test-model", {})
    mem_action_context.llm_service = mock_llm_service

    result = await mem_action_executor.execute("memory_extract", mem_action_context)

    assert result is not None
    assert result["extracted"] == 1  # Only the non-duplicate
    mock_mem_services["memory_manager"].remember.assert_called_once()


@pytest.mark.asyncio
async def test_memory_extract_disabled(mem_action_executor, mem_action_context, mock_mem_services):
    """Test memory extraction is skipped when auto_extract is disabled."""
    mock_mem_services["memory_manager"].config.enabled = True
    mock_mem_services["memory_manager"].config.auto_extract = False

    result = await mem_action_executor.execute("memory_extract", mem_action_context)

    assert result is None


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
    assert call_kwargs["use_semantic"] is True


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


class TestContentFingerprint:
    """Tests for _content_fingerprint helper function."""

    def test_content_fingerprint_returns_16_char_hash(self):
        """Test fingerprint returns a 16 character hex string."""
        result = _content_fingerprint("test content")
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_content_fingerprint_deterministic(self):
        """Test fingerprint is deterministic for same input."""
        content = "some test content here"
        result1 = _content_fingerprint(content)
        result2 = _content_fingerprint(content)
        assert result1 == result2

    def test_content_fingerprint_different_for_different_content(self):
        """Test fingerprint differs for different content."""
        result1 = _content_fingerprint("content A")
        result2 = _content_fingerprint("content B")
        assert result1 != result2


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


class TestMemoryExtractDirect:
    """Direct tests for memory_extract function."""

    @pytest.mark.asyncio
    async def test_memory_extract_no_memory_manager(self):
        """Test memory_extract returns None when memory_manager is None."""
        result = await memory_extract(
            memory_manager=None,
            llm_service=MagicMock(),
            session_manager=MagicMock(),
            session_id="test-session",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_memory_extract_config_disabled(self):
        """Test memory_extract returns None when config.enabled is False."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = False

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=MagicMock(),
            session_manager=MagicMock(),
            session_id="test-session",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_memory_extract_auto_extract_disabled(self):
        """Test memory_extract returns None when auto_extract is disabled."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.config.auto_extract = False

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=MagicMock(),
            session_manager=MagicMock(),
            session_id="test-session",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_memory_extract_no_llm_service(self):
        """Test memory_extract returns None when llm_service is None."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.config.auto_extract = True

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=None,
            session_manager=MagicMock(),
            session_id="test-session",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_memory_extract_session_not_found(self):
        """Test memory_extract returns None when session not found."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.config.auto_extract = True

        mock_session_manager = MagicMock()
        mock_session_manager.get.return_value = None

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=MagicMock(),
            session_manager=mock_session_manager,
            session_id="test-session",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_memory_extract_json_with_code_fence(self):
        """Test memory_extract handles JSON wrapped in code fences."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.config.auto_extract = True
        mock_memory_manager.config.extraction_prompt = "Extract: {summary}"
        mock_memory_manager.content_exists.return_value = False
        mock_memory_manager.remember = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem-123"
        mock_memory_manager.remember.return_value = mock_memory

        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.project_id = "proj-123"
        mock_session.summary_markdown = "Test summary"
        mock_session_manager.get.return_value = mock_session

        mock_provider = MagicMock()
        mock_provider.generate_text = AsyncMock(
            return_value='```json\n[{"content": "Test memory", "memory_type": "fact"}]\n```'
        )
        mock_llm_service = MagicMock()
        mock_llm_service.get_provider_for_feature.return_value = (
            mock_provider,
            "test-model",
            {},
        )

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=mock_llm_service,
            session_manager=mock_session_manager,
            session_id="test-session",
        )

        assert result is not None
        assert result["extracted"] == 1

    @pytest.mark.asyncio
    async def test_memory_extract_json_with_triple_backticks_only(self):
        """Test memory_extract handles JSON wrapped in backticks without json marker."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.config.auto_extract = True
        mock_memory_manager.config.extraction_prompt = "Extract: {summary}"
        mock_memory_manager.content_exists.return_value = False
        mock_memory_manager.remember = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem-123"
        mock_memory_manager.remember.return_value = mock_memory

        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.project_id = "proj-123"
        mock_session.summary_markdown = "Test summary"
        mock_session_manager.get.return_value = mock_session

        mock_provider = MagicMock()
        mock_provider.generate_text = AsyncMock(
            return_value='```\n[{"content": "Test memory", "memory_type": "fact"}]\n```'
        )
        mock_llm_service = MagicMock()
        mock_llm_service.get_provider_for_feature.return_value = (
            mock_provider,
            "test-model",
            {},
        )

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=mock_llm_service,
            session_manager=mock_session_manager,
            session_id="test-session",
        )

        assert result is not None
        assert result["extracted"] == 1

    @pytest.mark.asyncio
    async def test_memory_extract_json_parse_error(self):
        """Test memory_extract handles JSON parse errors."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.config.auto_extract = True
        mock_memory_manager.config.extraction_prompt = "Extract: {summary}"

        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.project_id = "proj-123"
        mock_session.summary_markdown = "Test summary"
        mock_session_manager.get.return_value = mock_session

        mock_provider = MagicMock()
        mock_provider.generate_text = AsyncMock(return_value="not valid json")
        mock_llm_service = MagicMock()
        mock_llm_service.get_provider_for_feature.return_value = (
            mock_provider,
            "test-model",
            {},
        )

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=mock_llm_service,
            session_manager=mock_session_manager,
            session_id="test-session",
        )

        assert result is not None
        assert result["extracted"] == 0
        assert result["error"] == "json_parse_error"

    @pytest.mark.asyncio
    async def test_memory_extract_invalid_response_format(self):
        """Test memory_extract handles non-list JSON response."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.config.auto_extract = True
        mock_memory_manager.config.extraction_prompt = "Extract: {summary}"

        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.project_id = "proj-123"
        mock_session.summary_markdown = "Test summary"
        mock_session_manager.get.return_value = mock_session

        mock_provider = MagicMock()
        mock_provider.generate_text = AsyncMock(return_value='{"not": "a list"}')
        mock_llm_service = MagicMock()
        mock_llm_service.get_provider_for_feature.return_value = (
            mock_provider,
            "test-model",
            {},
        )

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=mock_llm_service,
            session_manager=mock_session_manager,
            session_id="test-session",
        )

        assert result is not None
        assert result["extracted"] == 0
        assert result["error"] == "invalid_response_format"

    @pytest.mark.asyncio
    async def test_memory_extract_skips_non_dict_items(self):
        """Test memory_extract skips non-dict items in response list."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.config.auto_extract = True
        mock_memory_manager.config.extraction_prompt = "Extract: {summary}"
        mock_memory_manager.content_exists.return_value = False
        mock_memory_manager.remember = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem-123"
        mock_memory_manager.remember.return_value = mock_memory

        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.project_id = "proj-123"
        mock_session.summary_markdown = "Test summary"
        mock_session_manager.get.return_value = mock_session

        mock_provider = MagicMock()
        # Include a string, null, and valid dict
        mock_provider.generate_text = AsyncMock(
            return_value='["string item", null, {"content": "Valid memory", "memory_type": "fact"}]'
        )
        mock_llm_service = MagicMock()
        mock_llm_service.get_provider_for_feature.return_value = (
            mock_provider,
            "test-model",
            {},
        )

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=mock_llm_service,
            session_manager=mock_session_manager,
            session_id="test-session",
        )

        assert result is not None
        assert result["extracted"] == 1  # Only the valid dict

    @pytest.mark.asyncio
    async def test_memory_extract_skips_items_without_content(self):
        """Test memory_extract skips items without content field."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.config.auto_extract = True
        mock_memory_manager.config.extraction_prompt = "Extract: {summary}"
        mock_memory_manager.content_exists.return_value = False
        mock_memory_manager.remember = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem-123"
        mock_memory_manager.remember.return_value = mock_memory

        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.project_id = "proj-123"
        mock_session.summary_markdown = "Test summary"
        mock_session_manager.get.return_value = mock_session

        mock_provider = MagicMock()
        mock_provider.generate_text = AsyncMock(
            return_value='[{"memory_type": "fact"}, {"content": "", "memory_type": "fact"}, {"content": "Valid", "memory_type": "fact"}]'
        )
        mock_llm_service = MagicMock()
        mock_llm_service.get_provider_for_feature.return_value = (
            mock_provider,
            "test-model",
            {},
        )

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=mock_llm_service,
            session_manager=mock_session_manager,
            session_id="test-session",
        )

        assert result is not None
        assert result["extracted"] == 1  # Only the item with valid content

    @pytest.mark.asyncio
    async def test_memory_extract_normalizes_invalid_memory_type(self):
        """Test memory_extract normalizes invalid memory_type to 'fact'."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.config.auto_extract = True
        mock_memory_manager.config.extraction_prompt = "Extract: {summary}"
        mock_memory_manager.content_exists.return_value = False
        mock_memory_manager.remember = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem-123"
        mock_memory_manager.remember.return_value = mock_memory

        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.project_id = "proj-123"
        mock_session.summary_markdown = "Test summary"
        mock_session_manager.get.return_value = mock_session

        mock_provider = MagicMock()
        mock_provider.generate_text = AsyncMock(
            return_value='[{"content": "Test", "memory_type": "invalid_type"}]'
        )
        mock_llm_service = MagicMock()
        mock_llm_service.get_provider_for_feature.return_value = (
            mock_provider,
            "test-model",
            {},
        )

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=mock_llm_service,
            session_manager=mock_session_manager,
            session_id="test-session",
        )

        assert result is not None
        assert result["extracted"] == 1
        # Verify memory_type was normalized to 'fact'
        call_kwargs = mock_memory_manager.remember.call_args[1]
        assert call_kwargs["memory_type"] == "fact"

    @pytest.mark.asyncio
    async def test_memory_extract_normalizes_invalid_importance(self):
        """Test memory_extract normalizes invalid importance values."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.config.auto_extract = True
        mock_memory_manager.config.extraction_prompt = "Extract: {summary}"
        mock_memory_manager.content_exists.return_value = False
        mock_memory_manager.remember = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem-123"
        mock_memory_manager.remember.return_value = mock_memory

        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.project_id = "proj-123"
        mock_session.summary_markdown = "Test summary"
        mock_session_manager.get.return_value = mock_session

        mock_provider = MagicMock()
        mock_provider.generate_text = AsyncMock(
            return_value='[{"content": "Test", "importance": "not a number"}]'
        )
        mock_llm_service = MagicMock()
        mock_llm_service.get_provider_for_feature.return_value = (
            mock_provider,
            "test-model",
            {},
        )

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=mock_llm_service,
            session_manager=mock_session_manager,
            session_id="test-session",
        )

        assert result is not None
        assert result["extracted"] == 1
        # Verify importance was normalized to 0.5
        call_kwargs = mock_memory_manager.remember.call_args[1]
        assert call_kwargs["importance"] == 0.5

    @pytest.mark.asyncio
    async def test_memory_extract_clamps_importance(self):
        """Test memory_extract clamps importance to 0.0-1.0 range."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.config.auto_extract = True
        mock_memory_manager.config.extraction_prompt = "Extract: {summary}"
        mock_memory_manager.content_exists.return_value = False
        mock_memory_manager.remember = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem-123"
        mock_memory_manager.remember.return_value = mock_memory

        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.project_id = "proj-123"
        mock_session.summary_markdown = "Test summary"
        mock_session_manager.get.return_value = mock_session

        mock_provider = MagicMock()
        mock_provider.generate_text = AsyncMock(
            return_value='[{"content": "High", "importance": 1.5}, {"content": "Low", "importance": -0.5}]'
        )
        mock_llm_service = MagicMock()
        mock_llm_service.get_provider_for_feature.return_value = (
            mock_provider,
            "test-model",
            {},
        )

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=mock_llm_service,
            session_manager=mock_session_manager,
            session_id="test-session",
        )

        assert result is not None
        assert result["extracted"] == 2
        # Check both calls - importance should be clamped
        calls = mock_memory_manager.remember.call_args_list
        assert calls[0][1]["importance"] == 1.0  # Clamped from 1.5
        assert calls[1][1]["importance"] == 0.0  # Clamped from -0.5

    @pytest.mark.asyncio
    async def test_memory_extract_normalizes_invalid_tags(self):
        """Test memory_extract normalizes invalid tags to empty list."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.config.auto_extract = True
        mock_memory_manager.config.extraction_prompt = "Extract: {summary}"
        mock_memory_manager.content_exists.return_value = False
        mock_memory_manager.remember = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.id = "mem-123"
        mock_memory_manager.remember.return_value = mock_memory

        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.project_id = "proj-123"
        mock_session.summary_markdown = "Test summary"
        mock_session_manager.get.return_value = mock_session

        mock_provider = MagicMock()
        mock_provider.generate_text = AsyncMock(
            return_value='[{"content": "Test", "tags": "not a list"}]'
        )
        mock_llm_service = MagicMock()
        mock_llm_service.get_provider_for_feature.return_value = (
            mock_provider,
            "test-model",
            {},
        )

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=mock_llm_service,
            session_manager=mock_session_manager,
            session_id="test-session",
        )

        assert result is not None
        assert result["extracted"] == 1
        # Verify tags was normalized to empty list
        call_kwargs = mock_memory_manager.remember.call_args[1]
        assert call_kwargs["tags"] == []

    @pytest.mark.asyncio
    async def test_memory_extract_handles_remember_exception(self):
        """Test memory_extract handles exceptions from remember()."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.config.auto_extract = True
        mock_memory_manager.config.extraction_prompt = "Extract: {summary}"
        mock_memory_manager.content_exists.return_value = False
        mock_memory_manager.remember = AsyncMock(side_effect=Exception("DB error"))

        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.project_id = "proj-123"
        mock_session.summary_markdown = "Test summary"
        mock_session_manager.get.return_value = mock_session

        mock_provider = MagicMock()
        mock_provider.generate_text = AsyncMock(
            return_value='[{"content": "Test", "memory_type": "fact"}]'
        )
        mock_llm_service = MagicMock()
        mock_llm_service.get_provider_for_feature.return_value = (
            mock_provider,
            "test-model",
            {},
        )

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=mock_llm_service,
            session_manager=mock_session_manager,
            session_id="test-session",
        )

        assert result is not None
        assert result["extracted"] == 0  # Failed to create

    @pytest.mark.asyncio
    async def test_memory_extract_general_exception(self):
        """Test memory_extract handles general exceptions."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.config.enabled = True
        mock_memory_manager.config.auto_extract = True
        mock_memory_manager.config.extraction_prompt = "Extract: {summary}"

        mock_session_manager = MagicMock()
        mock_session = MagicMock()
        mock_session.project_id = "proj-123"
        mock_session.summary_markdown = "Test summary"
        mock_session_manager.get.return_value = mock_session

        mock_llm_service = MagicMock()
        mock_llm_service.get_provider_for_feature.side_effect = Exception("LLM error")

        result = await memory_extract(
            memory_manager=mock_memory_manager,
            llm_service=mock_llm_service,
            session_manager=mock_session_manager,
            session_id="test-session",
        )

        assert result is not None
        assert "error" in result
        assert "LLM error" in result["error"]


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
