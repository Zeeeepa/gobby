import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from gobby.tasks.context import ExpansionContext
from gobby.tasks.expansion import TaskExpander


@pytest.fixture
def mock_task_manager():
    return MagicMock()


@pytest.fixture
def mock_context():
    ctx = MagicMock(spec=ExpansionContext)
    ctx.relevant_files = []
    ctx.related_tasks = []
    ctx.web_research_results = []
    ctx.project_patterns = {}
    return ctx


@pytest.fixture
def mock_llm_service():
    service = MagicMock()
    service.generate_json.return_value = {
        "complexity_analysis": {"score": 3, "reasoning": "Simple task"},
        "phases": [
            {"name": "Phase 1", "subtasks": [{"title": "Subtask 1", "description": "Do this"}]}
        ],
    }
    return service


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.enabled = True
    config.max_subtasks = 10
    config.codebase_research_enabled = True  # Enabled globally
    config.web_research_enabled = True  # Enabled globally
    return config


@pytest.mark.asyncio
async def test_expansion_flow_defaults(
    mock_task_manager, mock_llm_service, mock_config, mock_context
):
    """Test expansion with default flags (web=False, code=True)."""

    # Mock gatherer to verify what it receives
    with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
        mock_gatherer_instance = MockGatherer.return_value
        # Use MagicMock specifically for the return value to avoid Pydantic validation errors
        mock_gatherer_instance.gather_context = AsyncMock(return_value=mock_context)

        # Initialize
        expander = TaskExpander(mock_config, mock_llm_service, mock_task_manager)
        # Verify gatherer initialized with same config/services
        MockGatherer.assert_called_with(
            task_manager=mock_task_manager,
            llm_service=mock_llm_service,
            config=mock_config,
            mcp_manager=None,
        )

        # Run
        await expander.expand_task(
            task_id="t1",
            title="Test Task",
            enable_web_research=False,  # Default explicit
            enable_code_context=True,  # Default explicit
        )

        from unittest.mock import ANY

        # Check gatherer call
        mock_gatherer_instance.gather_context.assert_called_with(
            ANY,  # Task object created internally
            enable_web_research=False,
            enable_code_context=True,
        )


@pytest.mark.asyncio
async def test_expansion_flow_with_web_research(
    mock_task_manager, mock_llm_service, mock_config, mock_context
):
    """Test expansion with web research enabled."""

    with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
        mock_gatherer_instance = MockGatherer.return_value
        mock_gatherer_instance.gather_context = AsyncMock(return_value=mock_context)

        expander = TaskExpander(mock_config, mock_llm_service, mock_task_manager)

        await expander.expand_task(
            task_id="t1", title="Test Task", enable_web_research=True, enable_code_context=True
        )

        from unittest.mock import ANY

        # Check gatherer call
        mock_gatherer_instance.gather_context.assert_called_with(
            ANY,
            enable_web_research=True,
            enable_code_context=True,
        )


@pytest.mark.asyncio
async def test_expansion_flow_no_code_context(
    mock_task_manager, mock_llm_service, mock_config, mock_context
):
    """Test expansion with code context disabled."""

    with patch("gobby.tasks.expansion.ExpansionContextGatherer") as MockGatherer:
        mock_gatherer_instance = MockGatherer.return_value
        mock_gatherer_instance.gather_context = AsyncMock(return_value=mock_context)

        expander = TaskExpander(mock_config, mock_llm_service, mock_task_manager)

        await expander.expand_task(
            task_id="t1", title="Test Task", enable_web_research=False, enable_code_context=False
        )

        from unittest.mock import ANY

        # Check gatherer call
        mock_gatherer_instance.gather_context.assert_called_with(
            ANY,
            enable_web_research=False,
            enable_code_context=False,
        )
