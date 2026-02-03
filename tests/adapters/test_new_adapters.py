"""Tests for new CLI adapters (Cursor, Windsurf, Copilot)."""

import pytest
from gobby.adapters.cursor import CursorAdapter
from gobby.adapters.windsurf import WindsurfAdapter
from gobby.adapters.copilot import CopilotAdapter
from gobby.hooks.events import SessionSource

pytestmark = pytest.mark.unit


class TestNewAdapters:
    """Tests for Cursor, Windsurf, and Copilot adapters."""

    def test_cursor_adapter_source(self) -> None:
        """CursorAdapter reports CURSOR as source."""
        adapter = CursorAdapter()
        assert adapter.source == SessionSource.CURSOR

    def test_windsurf_adapter_source(self) -> None:
        """WindsurfAdapter reports WINDSURF as source."""
        adapter = WindsurfAdapter()
        assert adapter.source == SessionSource.WINDSURF

    def test_copilot_adapter_source(self) -> None:
        """CopilotAdapter reports COPILOT as source."""
        adapter = CopilotAdapter()
        assert adapter.source == SessionSource.COPILOT

    def test_inheritance_from_claude(self) -> None:
        """New adapters inherit from ClaudeCodeAdapter functionality."""
        adapters = [CursorAdapter(), WindsurfAdapter(), CopilotAdapter()]

        for adapter in adapters:
            # Test that they have EVENT_MAP from ClaudeCodeAdapter
            assert "session-start" in adapter.EVENT_MAP
            assert "pre-tool-use" in adapter.EVENT_MAP

            # Test that they have translate methods
            assert hasattr(adapter, "translate_to_hook_event")
            assert hasattr(adapter, "translate_from_hook_response")
