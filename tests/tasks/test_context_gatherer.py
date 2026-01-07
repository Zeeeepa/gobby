from unittest.mock import MagicMock, patch

import pytest

from gobby.storage.tasks import Task
from gobby.tasks.context import ExpansionContextGatherer


@pytest.fixture
def mock_task_manager():
    return MagicMock()


@pytest.fixture
def sample_task():
    return Task(
        id="t1",
        project_id="p1",
        title="Implement login",
        status="open",
        priority=2,
        task_type="feature",
        created_at="now",
        updated_at="now",
        description="Implement login using auth.py",
    )


@pytest.mark.asyncio
async def test_gather_context_basic(mock_task_manager, sample_task):
    gatherer = ExpansionContextGatherer(mock_task_manager)

    # Mock finding related tasks
    mock_task_manager.list_tasks.return_value = [sample_task]

    # Mock filesystem operations
    with patch("gobby.tasks.context.find_project_root") as mock_root:
        mock_root.return_value = None  # Simulate no project root for simplicity first

        context = await gatherer.gather_context(sample_task)

        assert context.task.id == "t1"
        assert context.related_tasks == []  # Should be empty as we filter out same task
        assert context.relevant_files == []
        assert context.project_patterns == {}


@pytest.mark.asyncio
async def test_find_relevant_files_in_description(mock_task_manager, sample_task):
    gatherer = ExpansionContextGatherer(mock_task_manager)

    with patch("gobby.tasks.context.find_project_root") as mock_root:
        # Mock root path behavior
        mock_path = MagicMock()
        mock_root.return_value = mock_path

        # When checking relevant files, we look for "src/auth.py" in description
        # The regex looks for extensions. "auth.py" should match.
        mock_path.__truediv__.return_value = MagicMock(exists=lambda: False)

        def path_side_effect(arg):
            m = MagicMock()
            if str(arg).endswith("auth.py"):
                m.exists.return_value = True
                m.is_file.return_value = True
                m.resolve.return_value = m
                m.relative_to.return_value = "src/auth.py"
                # Mock parents for security check
                m.parents = [mock_path]
            else:
                m.exists.return_value = False
                m.resolve.return_value = m
                m.parents = [mock_path]
            return m

        mock_path.__truediv__.side_effect = path_side_effect
        # Mock resolve on the root itself if needed, but mostly on the result of /
        mock_path.resolve.return_value = mock_path

        # Update sample task description to have a clearer path or just filename
        sample_task.description = "Implement login using src/auth.py and ignore invalid.txt"

        files = await gatherer._find_relevant_files(sample_task)
        assert "src/auth.py" in files
        assert "invalid.txt" not in files  # txt not in our allowed extensions list

@pytest.mark.asyncio
async def test_gather_context_with_agentic_research(mock_task_manager, sample_task):
    from gobby.config.app import TaskExpansionConfig

    # Mock config and service
    config = TaskExpansionConfig(
        enabled=True,
        provider="claude",
        model="claude-test",
        codebase_research_enabled=True
    )
    llm_service = MagicMock()

    gatherer = ExpansionContextGatherer(mock_task_manager, llm_service, config)

    # Mock find_related and find_relevant (base)
    # We need to mock these properly because they are called
    # But since they are async, we need async mocks

    with patch.object(gatherer, '_find_related_tasks', return_value=[]), \
         patch.object(gatherer, '_find_relevant_files', return_value=[]), \
         patch.object(gatherer, '_read_file_snippets', return_value={}), \
         patch.object(gatherer, '_detect_project_patterns', return_value={}), \
         patch("gobby.tasks.research.TaskResearchAgent") as MockAgent:

        mock_agent_instance =  MockAgent.return_value

        # Simpler way to mock async return
        async def mock_run(*args, **kwargs):
            return {
                "relevant_files": ["agent_found.py"],
                "findings": "Found it"
            }
        mock_agent_instance.run.side_effect = mock_run

        context = await gatherer.gather_context(sample_task)

        # Verify agent was called
        # MockAgent(config, llm_service)
        call_args = MockAgent.call_args
        assert call_args[0][0] == config
        assert call_args[0][1] == llm_service

        # Verify results merged
        assert "agent_found.py" in context.relevant_files
        assert context.agent_findings == "Found it"
