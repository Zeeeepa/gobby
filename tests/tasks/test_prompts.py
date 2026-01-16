from gobby.config.app import TaskExpansionConfig
from gobby.storage.tasks import Task
from gobby.tasks.context import ExpansionContext
from gobby.tasks.prompts.expand import DEFAULT_SYSTEM_PROMPT, ExpansionPromptBuilder


def test_get_system_prompt_default():
    config = TaskExpansionConfig(enabled=True, provider="test", model="test")
    builder = ExpansionPromptBuilder(config)
    prompt = builder.get_system_prompt()
    # Should contain key content from the system prompt template
    assert "senior technical project manager" in prompt
    assert "JSON object containing a \"subtasks\" array" in prompt
    assert "## Validation Criteria Rules" in prompt


def test_get_system_prompt_custom():
    config = TaskExpansionConfig(
        enabled=True,
        provider="test",
        model="test",
        system_prompt="Custom Prompt",
    )
    builder = ExpansionPromptBuilder(config)
    assert builder.get_system_prompt() == "Custom Prompt"


def test_build_user_prompt_default():
    config = TaskExpansionConfig(enabled=True, provider="test", model="test")
    builder = ExpansionPromptBuilder(config)

    task = Task(
        id="t1",
        project_id="p1",
        title="My Task",
        description="My Desc",
        status="open",
        priority=2,
        task_type="feature",
        created_at="now",
        updated_at="now",
    )
    context = ExpansionContext(
        task=task,
        relevant_files=["file1.py"],
        project_patterns={"pat1": "val1"},
        related_tasks=[],
        file_snippets={},
    )

    prompt = builder.build_user_prompt(task, context)

    assert "My Task" in prompt
    assert "My Desc" in prompt
    assert "file1.py" in prompt
    assert "pat1: val1" in prompt
    assert "No research performed" in prompt


def test_build_user_prompt_with_instructions():
    config = TaskExpansionConfig(enabled=True, provider="test", model="test")
    builder = ExpansionPromptBuilder(config)

    task = Task(
        id="t1",
        project_id="p1",
        title="T1",
        status="open",
        priority=2,
        task_type="feature",
        created_at="now",
        updated_at="now",
    )
    context = ExpansionContext(
        task=task,
        related_tasks=[],
        relevant_files=[],
        file_snippets={},
        project_patterns={},
    )

    prompt = builder.build_user_prompt(task, context, user_instructions="Do it cleanly")

    assert "Do it cleanly" in prompt


def test_get_system_prompt_with_tdd_mode():
    """Test that TDD mode instructions are appended when enabled."""
    config = TaskExpansionConfig(enabled=True, provider="test", model="test")
    builder = ExpansionPromptBuilder(config)

    prompt_without_tdd = builder.get_system_prompt(tdd_mode=False)
    prompt_with_tdd = builder.get_system_prompt(tdd_mode=True)

    # TDD mode should append additional instructions
    assert len(prompt_with_tdd) > len(prompt_without_tdd)
    assert "TDD Mode Enabled" in prompt_with_tdd
    assert "TDD Mode Enabled" not in prompt_without_tdd
