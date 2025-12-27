import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from gobby.config.app import SkillConfig
from gobby.llm.service import LLMService
from gobby.memory.skills import SkillLearner
from gobby.storage.messages import LocalMessageManager
from gobby.storage.sessions import Session
from gobby.storage.skills import LocalSkillManager, Skill


@pytest.fixture
def mock_storage():
    return MagicMock(spec=LocalSkillManager)


@pytest.fixture
def mock_message_manager():
    return AsyncMock(spec=LocalMessageManager)


@pytest.fixture
def mock_llm_provider():
    provider = AsyncMock()
    provider.generate_text.return_value = "[]"
    return provider


@pytest.fixture
def mock_llm_service(mock_llm_provider):
    service = MagicMock(spec=LLMService)
    service.get_default_provider.return_value = mock_llm_provider
    return service


@pytest.fixture
def skill_config():
    return SkillConfig(enabled=True, auto_suggest=True, max_suggestions=3)


@pytest.fixture
def skill_learner(mock_storage, mock_message_manager, mock_llm_service, skill_config):
    return SkillLearner(mock_storage, mock_message_manager, mock_llm_service, skill_config)


@pytest.mark.asyncio
async def test_learn_from_session_empty_messages(skill_learner, mock_message_manager):
    session = MagicMock(spec=Session)
    session.id = "session_1"

    mock_message_manager.get_messages.return_value = []

    skills = await skill_learner.learn_from_session(session)

    assert len(skills) == 0
    assert not skill_learner.llm_service.get_default_provider.called


@pytest.mark.asyncio
async def test_learn_from_session_success(
    skill_learner, mock_message_manager, mock_storage, mock_llm_provider
):
    session = MagicMock(spec=Session)
    session.id = "session_1"
    session.project_id = "project_1"

    mock_message_manager.get_messages.return_value = [
        {"role": "user", "content": "how do I run tests?"},
        {"role": "assistant", "content": "use pytest"},
        {"role": "user", "content": "ok"},
        {"role": "assistant", "content": "cool"},
    ]

    # Mock LLM response
    mock_llm_provider.generate_text.return_value = """[
        {
            "name": "run-tests",
            "instructions": "Run pytest",
            "trigger_pattern": "test",
            "tags": ["testing"]
        }
    ]"""

    created_skill = Skill(
        id="sk-123",
        name="run-tests",
        instructions="Run pytest",
        created_at="now",
        updated_at="now",
        trigger_pattern="test",
    )
    mock_storage.create_skill.return_value = created_skill

    skills = await skill_learner.learn_from_session(session)

    assert len(skills) == 1
    assert skills[0] == created_skill
    mock_storage.create_skill.assert_called_once()
    assert mock_storage.create_skill.call_args.kwargs["project_id"] == "project_1"


@pytest.mark.asyncio
async def test_match_skills(skill_learner, mock_storage):
    skill1 = Skill(
        id="1", name="s1", instructions="i1", created_at="", updated_at="", trigger_pattern="test"
    )
    skill1.usage_count = 5
    skill2 = Skill(
        id="2", name="s2", instructions="i2", created_at="", updated_at="", trigger_pattern="build"
    )
    skill2.usage_count = 2

    mock_storage.list_skills.return_value = [skill1, skill2]

    # Match "test"
    matches = await skill_learner.match_skills("how to test?")
    assert len(matches) == 1
    assert matches[0] == skill1

    # Match "build"
    matches = await skill_learner.match_skills("run build")
    assert len(matches) == 1
    assert matches[0] == skill2

    # Match none
    matches = await skill_learner.match_skills("foo")
    assert len(matches) == 0


@pytest.mark.asyncio
async def test_record_usage(skill_learner, mock_storage):
    await skill_learner.record_usage("sk-123")
    mock_storage.increment_usage.assert_called_with("sk-123")
