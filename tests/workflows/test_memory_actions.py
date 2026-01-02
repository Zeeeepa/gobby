from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.memory.manager import MemoryManager
from gobby.skills import SkillLearner
from gobby.workflows.actions import ActionContext, ActionExecutor
from gobby.workflows.definitions import WorkflowState
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
        "skill_learner": AsyncMock(spec=SkillLearner),
        "memory_sync_manager": AsyncMock(),
    }
    # Manually attach config mocks because spec might strict on attributes not in class __init__
    services["memory_manager"].config = MagicMock()
    services["memory_manager"].config.enabled = True
    services["skill_learner"].config = MagicMock()
    services["skill_learner"].config.enabled = True
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
        skill_learner=mock_mem_services["skill_learner"],
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
        skill_learner=mock_mem_services["skill_learner"],
        memory_sync_manager=mock_mem_services["memory_sync_manager"],
    )


@pytest.mark.asyncio
async def test_memory_inject_recall(
    mem_action_executor, mem_action_context, session_manager, sample_project, mock_mem_services
):
    # Setup session
    session = session_manager.register(
        external_id="mem-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    mem_action_context.session_id = session.id
    mem_action_context.state.session_id = session.id

    # Mock recall
    mock_mem_services["memory_manager"].config.enabled = True
    mock_mem_services["memory_manager"].config.injection_limit = 10

    m1 = MagicMock()
    m1.memory_type = "fact"
    m1.content = "Memory 1"
    m2 = MagicMock()
    m2.memory_type = "learning"
    m2.content = "Memory 2"

    mock_mem_services["memory_manager"].recall.return_value = [m1, m2]

    # Execute - pass explicit limit to match assertion
    result = await mem_action_executor.execute(
        "memory_inject", mem_action_context, min_importance=0.7, limit=10
    )

    # Verify
    assert result is not None
    assert "inject_context" in result
    assert "Memory 1" in result["inject_context"]

    mock_mem_services["memory_manager"].recall.assert_called_with(
        project_id=str(sample_project["id"]), min_importance=0.7, limit=10
    )


@pytest.mark.asyncio
async def test_skills_learn(
    mem_action_executor, mem_action_context, session_manager, sample_project, mock_mem_services
):
    session = session_manager.register(
        external_id="learn-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    mem_action_context.session_id = session.id

    mock_mem_services["skill_learner"].config.enabled = True
    mock_skill = MagicMock()
    mock_skill.name = "NewSkill"
    mock_mem_services["skill_learner"].learn_from_session.return_value = [mock_skill]

    result = await mem_action_executor.execute("skills_learn", mem_action_context)

    assert result is not None
    assert result["skills_learned"] == 1
    mock_mem_services["skill_learner"].learn_from_session.assert_called_once()


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
    mock_provider.generate_text = AsyncMock(return_value='''[
        {"content": "User prefers pytest", "memory_type": "preference", "importance": 0.7},
        {"content": "Project uses Python 3.11", "memory_type": "fact", "importance": 0.6}
    ]''')
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
    mock_provider.generate_text = AsyncMock(return_value='''[
        {"content": "Existing memory", "memory_type": "fact", "importance": 0.5},
        {"content": "New memory", "memory_type": "fact", "importance": 0.5}
    ]''')
    mock_llm_service = MagicMock()
    mock_llm_service.get_provider_for_feature.return_value = (mock_provider, "test-model", {})
    mem_action_context.llm_service = mock_llm_service

    result = await mem_action_executor.execute("memory_extract", mem_action_context)

    assert result is not None
    assert result["extracted"] == 1  # Only the non-duplicate
    mock_mem_services["memory_manager"].remember.assert_called_once()


@pytest.mark.asyncio
async def test_memory_extract_disabled(
    mem_action_executor, mem_action_context, mock_mem_services
):
    """Test memory extraction is skipped when auto_extract is disabled."""
    mock_mem_services["memory_manager"].config.enabled = True
    mock_mem_services["memory_manager"].config.auto_extract = False

    result = await mem_action_executor.execute("memory_extract", mem_action_context)

    assert result is None


# --- Selective Injection Tests ---


@pytest.mark.asyncio
async def test_memory_inject_uses_config_threshold(
    mem_action_executor, mem_action_context, session_manager, sample_project, mock_mem_services
):
    """Test memory_inject uses config importance_threshold as default."""
    session = session_manager.register(
        external_id="threshold-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    mem_action_context.session_id = session.id
    mem_action_context.state.session_id = session.id

    # Set config threshold
    mock_mem_services["memory_manager"].config.enabled = True
    mock_mem_services["memory_manager"].config.importance_threshold = 0.7
    mock_mem_services["memory_manager"].config.injection_limit = 5

    m1 = MagicMock()
    m1.memory_type = "fact"
    m1.content = "High importance memory"
    mock_mem_services["memory_manager"].recall.return_value = [m1]

    # Call without min_importance kwarg - should use config default
    result = await mem_action_executor.execute("memory_inject", mem_action_context)

    assert result is not None
    assert "inject_context" in result
    # Verify recall was called with config threshold
    mock_mem_services["memory_manager"].recall.assert_called_with(
        project_id=str(sample_project["id"]),
        min_importance=0.7,
        limit=5,
    )


@pytest.mark.asyncio
async def test_memory_inject_enforces_limit(
    mem_action_executor, mem_action_context, session_manager, sample_project, mock_mem_services
):
    """Test memory_inject respects injection_limit from config."""
    session = session_manager.register(
        external_id="limit-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    mem_action_context.session_id = session.id
    mem_action_context.state.session_id = session.id

    mock_mem_services["memory_manager"].config.enabled = True
    mock_mem_services["memory_manager"].config.importance_threshold = 0.3
    mock_mem_services["memory_manager"].config.injection_limit = 3

    # Return 3 memories (limit)
    memories = [MagicMock(memory_type="fact", content=f"Memory {i}") for i in range(3)]
    mock_mem_services["memory_manager"].recall.return_value = memories

    result = await mem_action_executor.execute("memory_inject", mem_action_context)

    assert result is not None
    assert result["count"] == 3
    # Verify limit was passed to recall
    call_kwargs = mock_mem_services["memory_manager"].recall.call_args[1]
    assert call_kwargs["limit"] == 3


@pytest.mark.asyncio
async def test_memory_inject_kwargs_override_config(
    mem_action_executor, mem_action_context, session_manager, sample_project, mock_mem_services
):
    """Test that kwargs can override config values."""
    session = session_manager.register(
        external_id="override-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    mem_action_context.session_id = session.id
    mem_action_context.state.session_id = session.id

    # Config values
    mock_mem_services["memory_manager"].config.enabled = True
    mock_mem_services["memory_manager"].config.importance_threshold = 0.3
    mock_mem_services["memory_manager"].config.injection_limit = 10

    m1 = MagicMock(memory_type="fact", content="Memory")
    mock_mem_services["memory_manager"].recall.return_value = [m1]

    # Call with overriding kwargs
    result = await mem_action_executor.execute(
        "memory_inject",
        mem_action_context,
        min_importance=0.8,
        limit=2,
    )

    assert result is not None
    # Verify kwargs overrode config
    mock_mem_services["memory_manager"].recall.assert_called_with(
        project_id=str(sample_project["id"]),
        min_importance=0.8,
        limit=2,
    )


@pytest.mark.asyncio
async def test_memory_inject_returns_count(
    mem_action_executor, mem_action_context, session_manager, sample_project, mock_mem_services
):
    """Test memory_inject returns count for observability."""
    session = session_manager.register(
        external_id="count-ext",
        machine_id="test-machine",
        source="test-source",
        project_id=sample_project["id"],
    )
    mem_action_context.session_id = session.id
    mem_action_context.state.session_id = session.id

    mock_mem_services["memory_manager"].config.enabled = True
    mock_mem_services["memory_manager"].config.importance_threshold = 0.3
    mock_mem_services["memory_manager"].config.injection_limit = 10

    memories = [MagicMock(memory_type="fact", content=f"Memory {i}") for i in range(5)]
    mock_mem_services["memory_manager"].recall.return_value = memories

    result = await mem_action_executor.execute("memory_inject", mem_action_context)

    assert result is not None
    assert "count" in result
    assert result["count"] == 5


# --- memory_save Action Tests ---


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
