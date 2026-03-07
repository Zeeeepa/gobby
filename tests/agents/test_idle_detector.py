"""Tests for gobby.agents.idle_detector module."""

from __future__ import annotations

import time

import pytest

from gobby.agents.idle_detector import IdleDetector, IdleState

pytestmark = pytest.mark.unit


class TestDetect:
    """Tests for IdleDetector.detect()."""

    def setup_method(self) -> None:
        self.detector = IdleDetector()

    def test_empty_output_is_active(self) -> None:
        assert self.detector.detect("") == "active"
        assert self.detector.detect("   \n  \n") == "active"

    def test_claude_idle_prompt(self) -> None:
        output = "some output\nmore output\n❯\n"
        assert self.detector.detect(output) == "idle"

    def test_shell_prompt(self) -> None:
        output = "exited\n$\n"
        assert self.detector.detect(output) == "idle"

    def test_greater_than_prompt(self) -> None:
        output = "done\n>\n"
        assert self.detector.detect(output) == "idle"

    def test_active_output(self) -> None:
        output = "Running tests...\n  PASS test_foo.py\n  3 passed in 2.1s\n"
        assert self.detector.detect(output) == "active"

    def test_context_full_detection(self) -> None:
        output = "The context window is full. Would you like to start a new conversation?\n❯\n"
        assert self.detector.detect(output) == "context_full"

    def test_context_full_run_out(self) -> None:
        output = "I've run out of context space.\n"
        assert self.detector.detect(output) == "context_full"

    def test_context_full_conversation_too_long(self) -> None:
        output = "This conversation is too long to continue.\n"
        assert self.detector.detect(output) == "context_full"

    def test_context_full_takes_priority_over_idle(self) -> None:
        """Context full should be detected even if last line is idle prompt."""
        output = "Would you like to continue?\n❯\n"
        assert self.detector.detect(output) == "context_full"

    def test_idle_prompt_with_whitespace(self) -> None:
        output = "done\n  ❯  \n"
        assert self.detector.detect(output) == "idle"

    def test_non_idle_last_line(self) -> None:
        output = "Processing file 3 of 10...\n"
        assert self.detector.detect(output) == "active"


class TestShouldReprompt:
    """Tests for reprompt timing logic."""

    def setup_method(self) -> None:
        self.detector = IdleDetector()

    def test_first_idle_records_time_no_reprompt(self) -> None:
        """First idle detection should not trigger reprompt."""
        assert not self.detector.should_reprompt("run-1", 60, 3)
        state = self.detector.get_state("run-1")
        assert state.first_idle_at is not None

    def test_reprompt_after_timeout(self) -> None:
        """Should reprompt after idle timeout elapsed."""
        state = self.detector.get_state("run-1")
        state.first_idle_at = time.monotonic() - 120  # 2 minutes ago
        assert self.detector.should_reprompt("run-1", 60, 3)

    def test_no_reprompt_before_timeout(self) -> None:
        """Should not reprompt before timeout."""
        state = self.detector.get_state("run-1")
        state.first_idle_at = time.monotonic() - 10  # 10 seconds ago
        assert not self.detector.should_reprompt("run-1", 60, 3)

    def test_no_reprompt_after_max_attempts(self) -> None:
        """Should not reprompt after max attempts reached."""
        state = self.detector.get_state("run-1")
        state.first_idle_at = time.monotonic() - 120
        state.reprompt_count = 3
        assert not self.detector.should_reprompt("run-1", 60, 3)


class TestShouldFail:
    """Tests for failure detection."""

    def setup_method(self) -> None:
        self.detector = IdleDetector()

    def test_should_fail_at_max_attempts(self) -> None:
        state = self.detector.get_state("run-1")
        state.reprompt_count = 3
        assert self.detector.should_fail("run-1", 3)

    def test_should_not_fail_below_max(self) -> None:
        state = self.detector.get_state("run-1")
        state.reprompt_count = 2
        assert not self.detector.should_fail("run-1", 3)


class TestRecordReprompt:
    """Tests for reprompt recording."""

    def setup_method(self) -> None:
        self.detector = IdleDetector()

    def test_increments_count(self) -> None:
        self.detector.record_reprompt("run-1")
        state = self.detector.get_state("run-1")
        assert state.reprompt_count == 1
        assert state.last_reprompt_at is not None

    def test_resets_idle_timer(self) -> None:
        """Recording reprompt should reset the idle start time."""
        state = self.detector.get_state("run-1")
        state.first_idle_at = time.monotonic() - 300
        old_idle = state.first_idle_at
        self.detector.record_reprompt("run-1")
        assert state.first_idle_at > old_idle


class TestResetIdle:
    """Tests for idle state reset."""

    def setup_method(self) -> None:
        self.detector = IdleDetector()

    def test_clears_idle_start(self) -> None:
        state = self.detector.get_state("run-1")
        state.first_idle_at = time.monotonic()
        self.detector.reset_idle("run-1")
        assert state.first_idle_at is None

    def test_preserves_reprompt_count(self) -> None:
        """Reset should not clear reprompt count."""
        state = self.detector.get_state("run-1")
        state.reprompt_count = 2
        state.first_idle_at = time.monotonic()
        self.detector.reset_idle("run-1")
        assert state.reprompt_count == 2


class TestClearState:
    """Tests for state cleanup."""

    def setup_method(self) -> None:
        self.detector = IdleDetector()

    def test_removes_state(self) -> None:
        self.detector.get_state("run-1")
        self.detector.clear_state("run-1")
        # Should create fresh state
        state = self.detector.get_state("run-1")
        assert state.first_idle_at is None
        assert state.reprompt_count == 0

    def test_clear_nonexistent_is_noop(self) -> None:
        self.detector.clear_state("no-such-run")  # should not raise


class TestStatusBarFiltering:
    """Tests for idle detection through Claude Code status bar."""

    def setup_method(self) -> None:
        self.detector = IdleDetector()

    def test_idle_prompt_above_status_bar(self) -> None:
        """The real-world case: ❯ prompt is above the status bar."""
        output = (
            "⏺ All 34 tests pass.\n"
            "\n"
            "❯ \n"
            "────────────────────\n"
            "   Opus 4.6  34.2%  3hr 22m \n"
            "   ⎇ epic-9915  𖠰 epic-9915  (+25,-26) \n"
            "   /private/tmp/gobby-worktrees/gobby/epic-9915 \n"
            "  ⏵⏵ bypass permissions on (shift+tab to cycle)\n"
        )
        assert self.detector.detect(output) == "idle"

    def test_active_output_above_status_bar(self) -> None:
        """Agent is working — last content line is not a prompt."""
        output = (
            "⏺ Bash(uv run pytest tests/ -v)\n"
            "────────────────────\n"
            "   Opus 4.6  34.2%  3hr \n"
            "   ⎇ epic-9915\n"
            "   /private/tmp/gobby-worktrees/gobby/epic-9915\n"
            "  ⏵⏵ bypass permissions on\n"
        )
        assert self.detector.detect(output) == "active"

    def test_status_bar_only_is_active(self) -> None:
        """If only status bar lines are captured, treat as active (can't tell)."""
        output = (
            "   Opus 4.6  34.2%  3hr \n"
            "   ⎇ epic-9915\n"
            "   /private/tmp/worktrees/epic\n"
            "  ⏵⏵ bypass permissions on\n"
        )
        assert self.detector.detect(output) == "active"
