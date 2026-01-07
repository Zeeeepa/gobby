"""Tests for the Code Guardian example plugin."""

# Import the plugin - need to add examples to path
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "examples" / "plugins"))

from code_guardian import CodeGuardianPlugin

from gobby.hooks.events import HookEvent, HookEventType, HookResponse, SessionSource

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def plugin() -> CodeGuardianPlugin:
    """Create a configured plugin instance."""
    p = CodeGuardianPlugin()
    p.on_load({
        "checks": ["ruff"],
        "block_on_error": True,
        "auto_fix": False,
    })
    return p


@pytest.fixture
def write_event() -> HookEvent:
    """Create a Write tool event."""
    return HookEvent(
        event_type=HookEventType.BEFORE_TOOL,
        session_id="test-session",
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC).isoformat(),
        data={
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/tmp/test.py",
                "content": "def foo():\n    pass\n",
            },
        },
    )


@pytest.fixture
def edit_event() -> HookEvent:
    """Create an Edit tool event."""
    return HookEvent(
        event_type=HookEventType.BEFORE_TOOL,
        session_id="test-session",
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC).isoformat(),
        data={
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/tmp/test.py",
                "old_string": "pass",
                "new_string": "return 42",
            },
        },
    )


# =============================================================================
# Plugin Lifecycle Tests
# =============================================================================


class TestPluginLifecycle:
    """Tests for plugin initialization and lifecycle."""

    def test_plugin_has_required_attributes(self):
        """Test that plugin has required name and version."""
        plugin = CodeGuardianPlugin()
        assert plugin.name == "code-guardian"
        assert plugin.version == "1.0.0"
        assert "quality" in plugin.description.lower() or "guardian" in plugin.description.lower()

    def test_on_load_sets_config(self):
        """Test that on_load configures the plugin."""
        plugin = CodeGuardianPlugin()
        plugin.on_load({
            "checks": ["ruff", "mypy"],
            "block_on_error": False,
            "auto_fix": True,
        })

        assert plugin.checks == ["ruff", "mypy"]
        assert plugin.block_on_error is False
        assert plugin.auto_fix is True

    def test_on_load_uses_defaults(self):
        """Test that on_load uses defaults for missing config."""
        plugin = CodeGuardianPlugin()
        plugin.on_load({})

        assert plugin.checks == ["ruff"]
        assert plugin.block_on_error is True
        assert plugin.auto_fix is True

    def test_registers_actions_and_conditions(self):
        """Test that plugin registers workflow extensions."""
        plugin = CodeGuardianPlugin()
        plugin.on_load({})

        assert "run_linter" in plugin._actions
        assert "format_code" in plugin._actions
        assert "passes_lint" in plugin._conditions
        assert "has_type_errors" in plugin._conditions


# =============================================================================
# Hook Handler Tests
# =============================================================================


class TestPreHandler:
    """Tests for the BEFORE_TOOL handler."""

    def test_ignores_non_edit_write_tools(self, plugin):
        """Test that non-Edit/Write tools are ignored."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="test",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC).isoformat(),
            data={"tool_name": "Read", "tool_input": {"file_path": "/tmp/test.py"}},
        )

        result = plugin.check_before_write(event)
        assert result is None

    def test_ignores_non_python_files(self, plugin):
        """Test that non-Python files are ignored."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="test",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC).isoformat(),
            data={
                "tool_name": "Write",
                "tool_input": {
                    "file_path": "/tmp/test.txt",
                    "content": "hello world",
                },
            },
        )

        result = plugin.check_before_write(event)
        assert result is None

    def test_ignores_venv_paths(self, plugin):
        """Test that .venv paths are ignored."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="test",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC).isoformat(),
            data={
                "tool_name": "Write",
                "tool_input": {
                    "file_path": "/project/.venv/lib/test.py",
                    "content": "import os",
                },
            },
        )

        result = plugin.check_before_write(event)
        assert result is None

    def test_allows_clean_code(self, plugin, write_event):
        """Test that clean code is allowed."""
        result = plugin.check_before_write(write_event)
        assert result is None

    def test_blocks_code_with_debug_prints(self, plugin):
        """Test that code with debug prints is blocked."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="test",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC).isoformat(),
            data={
                "tool_name": "Write",
                "tool_input": {
                    "file_path": "/tmp/test.py",
                    "content": "def foo():\n    print(x)\n    return x\n",
                },
            },
        )

        result = plugin.check_before_write(event)
        assert result is not None
        assert result.decision == "deny"
        assert "blocked" in result.reason.lower()

    def test_allows_print_with_noqa(self, plugin):
        """Test that print with noqa comment is allowed."""
        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id="test",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC).isoformat(),
            data={
                "tool_name": "Write",
                "tool_input": {
                    "file_path": "/tmp/test.py",
                    "content": "def foo():\n    print(x)  # noqa\n    return x\n",
                },
            },
        )

        result = plugin.check_before_write(event)
        assert result is None

    def test_edit_tool_passes_through(self, plugin, edit_event):
        """Test that Edit tool is not checked in pre-handler."""
        # Edit tools are checked in post-handler after the edit is applied
        result = plugin.check_before_write(edit_event)
        assert result is None


# =============================================================================
# Post Handler Tests
# =============================================================================


class TestPostHandler:
    """Tests for the AFTER_TOOL handler."""

    def test_ignores_non_edit_write_tools(self, plugin):
        """Test that post-handler ignores non-Edit/Write tools."""
        event = HookEvent(
            event_type=HookEventType.AFTER_TOOL,
            session_id="test",
            source=SessionSource.CLAUDE,
            timestamp=datetime.now(UTC).isoformat(),
            data={"tool_name": "Bash", "tool_input": {"command": "ls"}},
        )

        # Should not raise, just return None
        plugin.report_after_tool(event, None)

    def test_checks_file_after_edit(self, plugin):
        """Test that files are checked after Edit."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"def foo():\n    pass\n")
            f.flush()

            event = HookEvent(
                event_type=HookEventType.AFTER_TOOL,
                session_id="test",
                source=SessionSource.CLAUDE,
                timestamp=datetime.now(UTC).isoformat(),
                data={
                    "tool_name": "Edit",
                    "tool_input": {"file_path": f.name},
                },
            )

            plugin.report_after_tool(event, HookResponse(decision="allow"))
            assert plugin._files_checked == 1


# =============================================================================
# Workflow Action Tests
# =============================================================================


class TestWorkflowActions:
    """Tests for workflow actions."""

    @pytest.mark.asyncio
    async def test_run_linter_on_files(self, plugin):
        """Test run_linter action on test files."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"def foo():\n    pass\n")
            f.flush()

            result = await plugin._action_run_linter({}, files=[f.name])

            assert "passed" in result
            assert "errors" in result
            assert "files_checked" in result
            assert result["files_checked"] == 1

    @pytest.mark.asyncio
    async def test_run_linter_empty_files(self, plugin):
        """Test run_linter with no files."""
        result = await plugin._action_run_linter({}, files=[])
        assert result["files_checked"] == 0
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_format_code_missing_ruff(self, plugin):
        """Test format_code when ruff is not available."""
        with patch("shutil.which", return_value=None):
            result = await plugin._action_format_code({}, files=["/tmp/test.py"])
            assert result["formatted"] == 0
            assert "ruff not found" in result["errors"][0]


# =============================================================================
# Workflow Condition Tests
# =============================================================================


class TestWorkflowConditions:
    """Tests for workflow conditions."""

    def test_passes_lint_no_checks(self, plugin):
        """Test passes_lint when no files have been checked."""
        assert plugin._condition_passes_lint() is True

    def test_passes_lint_after_failure(self, plugin):
        """Test passes_lint after a failed check."""
        plugin._last_check_results["/tmp/test.py"] = {
            "status": "failed",
            "errors": ["E001: error"],
        }
        assert plugin._condition_passes_lint() is False

    def test_passes_lint_after_success(self, plugin):
        """Test passes_lint after a successful check."""
        plugin._last_check_results["/tmp/test.py"] = {"status": "passed"}
        assert plugin._condition_passes_lint() is True

    def test_passes_lint_specific_file(self, plugin):
        """Test passes_lint for a specific file."""
        plugin._last_check_results["/tmp/good.py"] = {"status": "passed"}
        plugin._last_check_results["/tmp/bad.py"] = {"status": "failed", "errors": []}

        assert plugin._condition_passes_lint("/tmp/good.py") is True
        assert plugin._condition_passes_lint("/tmp/bad.py") is False
        assert plugin._condition_passes_lint("/tmp/unknown.py") is False


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests with the plugin registry."""

    def test_can_be_registered(self, plugin):
        """Test that plugin can be registered in a PluginRegistry."""
        from gobby.hooks.plugins import PluginRegistry

        registry = PluginRegistry()
        registry.register_plugin(plugin)

        assert registry.get_plugin("code-guardian") is plugin

        # Check handlers are registered
        before_handlers = registry.get_handlers(HookEventType.BEFORE_TOOL)
        after_handlers = registry.get_handlers(HookEventType.AFTER_TOOL)

        assert len(before_handlers) == 1
        assert before_handlers[0].priority == 10

        assert len(after_handlers) == 1
        assert after_handlers[0].priority == 60

    def test_handler_signatures_are_correct(self, plugin):
        """Test that handler method signatures match expectations."""
        import inspect

        # Pre-handler should accept (self, event)
        pre_sig = inspect.signature(plugin.check_before_write)
        pre_params = list(pre_sig.parameters.keys())
        assert pre_params == ["event"]

        # Post-handler should accept (self, event, core_response)
        post_sig = inspect.signature(plugin.report_after_tool)
        post_params = list(post_sig.parameters.keys())
        assert post_params == ["event", "core_response"]
