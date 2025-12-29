"""
Tests for TaskResearchAgent.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from gobby.config.app import TaskExpansionConfig
from gobby.tasks.research import TaskResearchAgent
from gobby.storage.tasks import Task


@pytest.fixture
def mock_config():
    return TaskExpansionConfig(
        enabled=True,
        provider="claude",
        model="claude-test",
        codebase_research_enabled=True,
        research_max_steps=5,
    )


@pytest.fixture
def mock_llm_service():
    service = MagicMock()
    provider = AsyncMock()
    service.get_provider.return_value = provider
    return service


@pytest.fixture
def mock_task():
    return Task(
        id="task-1",
        project_id="proj-1",
        title="Test Task",
        description="Implement login",
        status="open",
        priority=1,
        task_type="task",
        created_at="now",
        updated_at="now",
    )


@pytest.mark.asyncio
async def test_research_agent_initialization(mock_config, mock_llm_service):
    agent = TaskResearchAgent(mock_config, mock_llm_service)
    assert agent.config == mock_config
    assert agent.llm_service == mock_llm_service
    assert agent.max_steps == 10  # Default hardcoded in init unless we change init to use config


@pytest.mark.asyncio
async def test_research_run_success(mock_config, mock_llm_service, mock_task):
    agent = TaskResearchAgent(mock_config, mock_llm_service)

    # Mock LLM responses
    provider = mock_llm_service.get_provider.return_value
    provider.generate_text.side_effect = [
        "THOUGHT: I should look for files.\nACTION: glob('src/**/*.py')",
        "THOUGHT: I found files.\nACTION: done('Found them')",
    ]

    # Mock tools
    with patch.object(agent, "_glob", return_value="src/main.py") as mock_glob:
        result = await agent.run(mock_task)

        assert result["findings"] == "Agent research completed."
        assert len(result["relevant_files"]) == 0  # we didn't use read_file
        assert len(result["raw_history"]) >= 3  # 2 model turns (glob, done) + 1 tool output (glob)

        mock_glob.assert_called_once_with("src/**/*.py")


@pytest.mark.asyncio
async def test_research_read_file_populates_relevant_files(
    mock_config, mock_llm_service, mock_task
):
    agent = TaskResearchAgent(mock_config, mock_llm_service)

    provider = mock_llm_service.get_provider.return_value
    provider.generate_text.side_effect = [
        "ACTION: read_file('src/main.py')",
        "ACTION: done('Done')",
    ]

    with patch.object(agent, "_read_file", return_value="content") as mock_read:
        result = await agent.run(mock_task)

        assert "src/main.py" in result["relevant_files"]


@pytest.mark.asyncio
async def test_glob_tool(mock_config, mock_llm_service):
    agent = TaskResearchAgent(mock_config, mock_llm_service)

    # Mock root and glob
    with patch("pathlib.Path.glob") as mock_glob_path:
        mock_path1 = MagicMock()
        mock_path1.is_file.return_value = True
        mock_path1.relative_to.return_value = Path("src/test.py")

        mock_glob_path.return_value = [mock_path1]

        agent.root = Path("/root")

        result = agent._glob("src/*.py")
        assert "src/test.py" in result


def test_parse_action(mock_config, mock_llm_service):
    agent = TaskResearchAgent(mock_config, mock_llm_service)

    # Standard format
    assert agent._parse_action("ACTION: glob('*.py')") == {"tool": "glob", "args": ["*.py"]}
    assert agent._parse_action("Action: read_file('foo.txt')") == {
        "tool": "read_file",
        "args": ["foo.txt"],
    }

    # Multiple args
    assert agent._parse_action("ACTION: grep('def foo', 'src')") == {
        "tool": "grep",
        "args": ["def foo", "src"],
    }

    # Quotes handling
    assert agent._parse_action("ACTION: grep(\"def foo\", 'src')") == {
        "tool": "grep",
        "args": ["def foo", "src"],
    }

    # Fallback done
    assert agent._parse_action("I am done now") == {"tool": "done", "reason": "I am done now"}
