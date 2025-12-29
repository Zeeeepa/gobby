from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.mcp_proxy.tools.memory import create_memory_registry
from gobby.mcp_proxy.tools.skills import create_skills_registry
from gobby.memory.manager import MemoryManager
from gobby.skills import SkillLearner
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.skills import LocalSkillManager


@pytest.fixture
def mock_memory_manager():
    manager = MagicMock(spec=MemoryManager)
    manager.remember.return_value = MagicMock(
        id="mem_1", content="test", memory_type="fact", importance=0.5, tags=[]
    )
    manager.recall.return_value = []
    manager.forget.return_value = True
    return manager


@pytest.fixture
def mock_skill_components():
    storage = MagicMock(spec=LocalSkillManager)
    learner = AsyncMock(spec=SkillLearner)
    learner.storage = storage  # Link storage to learner
    manager = MagicMock(spec=LocalSessionManager)
    return storage, learner, manager


def test_memory_registry_creation(mock_memory_manager):
    registry = create_memory_registry(mock_memory_manager)
    assert registry.name == "gobby-memory"

    tools = registry.list_tools()
    tool_names = {t["name"] for t in tools}
    assert "remember" in tool_names
    assert "recall" in tool_names
    assert "forget" in tool_names


def test_skills_registry_creation(mock_skill_components):
    storage, learner, session_manager = mock_skill_components

    # Test with full components
    registry = create_skills_registry(storage, learner, session_manager)
    assert registry.name == "gobby-skills"

    tools = registry.list_tools()
    tool_names = {t["name"] for t in tools}
    assert "learn_skill_from_session" in tool_names
    assert "list_skills" in tool_names
    assert "get_skill" in tool_names
    assert "delete_skill" in tool_names


@pytest.mark.asyncio
async def test_skills_registry_llm_check(mock_skill_components):
    storage, _, session_manager = mock_skill_components

    # Test WITHOUT learner (simulating stdio environment)
    registry = create_skills_registry(storage, learner=None, session_manager=session_manager)

    # Non-LLM tools should work
    storage.list_skills.return_value = []
    await registry.call("list_skills", {})
    storage.list_skills.assert_called_once()

    # LLM tools should raise RuntimeError
    with pytest.raises(RuntimeError, match="requires LLM"):
        await registry.call("learn_skill_from_session", {"session_id": "sess_1"})
