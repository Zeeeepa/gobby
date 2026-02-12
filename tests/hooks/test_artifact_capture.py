"""Tests for artifact capture hook with title generation and task inference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from gobby.hooks.artifact_capture import ArtifactCaptureHook

pytestmark = pytest.mark.unit


@dataclass
class FakeArtifact:
    id: str
    session_id: str
    artifact_type: str
    content: str
    created_at: str
    metadata: dict[str, Any] | None = None
    title: str | None = None
    task_id: str | None = None


@dataclass
class FakeTask:
    id: str
    status: str


@pytest.fixture
def artifact_manager() -> MagicMock:
    mgr = MagicMock()
    call_count = 0

    def fake_create(**kwargs: Any) -> FakeArtifact:
        nonlocal call_count
        call_count += 1
        return FakeArtifact(
            id=f"art-{call_count}",
            session_id=kwargs.get("session_id", "sess-1"),
            artifact_type=kwargs.get("artifact_type", "code"),
            content=kwargs.get("content", ""),
            created_at="2025-01-01T00:00:00",
            metadata=kwargs.get("metadata"),
            title=kwargs.get("title"),
            task_id=kwargs.get("task_id"),
        )

    mgr.create_artifact.side_effect = fake_create
    return mgr


@pytest.fixture
def session_task_manager() -> MagicMock:
    return MagicMock()


@pytest.fixture
def hook(artifact_manager: MagicMock, session_task_manager: MagicMock) -> ArtifactCaptureHook:
    return ArtifactCaptureHook(
        artifact_manager=artifact_manager,
        session_task_manager=session_task_manager,
    )


# =============================================================================
# Title generation
# =============================================================================


class TestGenerateTitle:
    def test_file_path_uses_filename(self, hook: ArtifactCaptureHook) -> None:
        title = hook._generate_title("/src/gobby/hooks/factory.py", "file_path")
        assert title == "factory.py"

    def test_file_path_no_slash(self, hook: ArtifactCaptureHook) -> None:
        title = hook._generate_title("README.md", "file_path")
        assert title == "README.md"

    def test_error_uses_first_line(self, hook: ArtifactCaptureHook) -> None:
        content = "ValueError: invalid literal\n  at line 42\n  at line 10"
        title = hook._generate_title(content, "error")
        assert title == "ValueError: invalid literal"

    def test_error_truncates_long_line(self, hook: ArtifactCaptureHook) -> None:
        content = "X" * 200
        title = hook._generate_title(content, "error")
        assert title is not None
        assert len(title) == 80

    def test_code_uses_first_nonempty_line(self, hook: ArtifactCaptureHook) -> None:
        content = "\n\ndef hello():\n    pass"
        title = hook._generate_title(content, "code")
        assert title == "def hello():"

    def test_code_truncates_long_line(self, hook: ArtifactCaptureHook) -> None:
        content = "x = " + "a" * 200
        title = hook._generate_title(content, "code")
        assert title is not None
        assert len(title) == 80

    def test_empty_content_returns_none(self, hook: ArtifactCaptureHook) -> None:
        assert hook._generate_title("", "code") is None
        assert hook._generate_title("   ", "code") is None

    def test_diff_uses_first_line(self, hook: ArtifactCaptureHook) -> None:
        content = "--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,3 @@"
        title = hook._generate_title(content, "diff")
        assert title == "--- a/file.py"


# =============================================================================
# Active task inference
# =============================================================================


class TestGetActiveTaskId:
    def test_returns_in_progress_task(
        self, hook: ArtifactCaptureHook, session_task_manager: MagicMock
    ) -> None:
        session_task_manager.get_session_tasks.return_value = [
            {"task": FakeTask(id="task-1", status="in_progress"), "action": "worked_on"},
        ]
        assert hook._get_active_task_id("sess-1") == "task-1"

    def test_skips_non_in_progress(
        self, hook: ArtifactCaptureHook, session_task_manager: MagicMock
    ) -> None:
        session_task_manager.get_session_tasks.return_value = [
            {"task": FakeTask(id="task-1", status="open"), "action": "worked_on"},
            {"task": FakeTask(id="task-2", status="closed"), "action": "worked_on"},
        ]
        assert hook._get_active_task_id("sess-1") is None

    def test_skips_non_worked_on_action(
        self, hook: ArtifactCaptureHook, session_task_manager: MagicMock
    ) -> None:
        session_task_manager.get_session_tasks.return_value = [
            {"task": FakeTask(id="task-1", status="in_progress"), "action": "mentioned"},
        ]
        assert hook._get_active_task_id("sess-1") is None

    def test_returns_none_without_manager(self, artifact_manager: MagicMock) -> None:
        hook = ArtifactCaptureHook(artifact_manager=artifact_manager)
        assert hook._get_active_task_id("sess-1") is None

    def test_handles_exception_gracefully(
        self, hook: ArtifactCaptureHook, session_task_manager: MagicMock
    ) -> None:
        session_task_manager.get_session_tasks.side_effect = RuntimeError("db error")
        assert hook._get_active_task_id("sess-1") is None


# =============================================================================
# process_message with title and task_id
# =============================================================================


class TestProcessMessageEnhancements:
    def test_code_block_gets_title(
        self, hook: ArtifactCaptureHook, artifact_manager: MagicMock, session_task_manager: MagicMock
    ) -> None:
        session_task_manager.get_session_tasks.return_value = []
        content = "Here's some code:\n```python\ndef hello():\n    print('hi')\n```"
        artifacts = hook.process_message("sess-1", "assistant", content)

        assert artifacts is not None
        assert len(artifacts) == 1
        # Verify title was passed to create_artifact
        call_kwargs = artifact_manager.create_artifact.call_args.kwargs
        assert call_kwargs["title"] == "def hello():"

    def test_code_block_gets_task_id(
        self, hook: ArtifactCaptureHook, artifact_manager: MagicMock, session_task_manager: MagicMock
    ) -> None:
        session_task_manager.get_session_tasks.return_value = [
            {"task": FakeTask(id="task-42", status="in_progress"), "action": "worked_on"},
        ]
        content = "```python\nx = 1\n```"
        hook.process_message("sess-1", "assistant", content)

        call_kwargs = artifact_manager.create_artifact.call_args.kwargs
        assert call_kwargs["task_id"] == "task-42"

    def test_file_path_gets_title(
        self, hook: ArtifactCaptureHook, artifact_manager: MagicMock, session_task_manager: MagicMock
    ) -> None:
        session_task_manager.get_session_tasks.return_value = []
        content = "Check `/src/gobby/hooks/factory.py` for details."
        artifacts = hook.process_message("sess-1", "assistant", content)

        assert artifacts is not None
        assert len(artifacts) == 1
        call_kwargs = artifact_manager.create_artifact.call_args.kwargs
        assert call_kwargs["title"] == "factory.py"
        assert call_kwargs["task_id"] is None

    def test_no_task_id_when_no_active_task(
        self, hook: ArtifactCaptureHook, artifact_manager: MagicMock, session_task_manager: MagicMock
    ) -> None:
        session_task_manager.get_session_tasks.return_value = []
        content = "```js\nconsole.log('test')\n```"
        hook.process_message("sess-1", "assistant", content)

        call_kwargs = artifact_manager.create_artifact.call_args.kwargs
        assert call_kwargs["task_id"] is None

    def test_user_messages_still_skipped(self, hook: ArtifactCaptureHook) -> None:
        result = hook.process_message("sess-1", "user", "```python\nx = 1\n```")
        assert result is None

    def test_task_id_shared_across_artifacts_in_same_message(
        self, hook: ArtifactCaptureHook, artifact_manager: MagicMock, session_task_manager: MagicMock
    ) -> None:
        session_task_manager.get_session_tasks.return_value = [
            {"task": FakeTask(id="task-99", status="in_progress"), "action": "worked_on"},
        ]
        content = "```python\ndef a(): pass\n```\n\n```js\nconst b = 1\n```"
        artifacts = hook.process_message("sess-1", "assistant", content)

        assert artifacts is not None
        assert len(artifacts) == 2
        for call in artifact_manager.create_artifact.call_args_list:
            assert call.kwargs["task_id"] == "task-99"
