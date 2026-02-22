"""Tests for trigger key map in unified_evaluator.py."""

import pytest

from gobby.hooks.events import HookEventType

pytestmark = pytest.mark.unit


class TestTriggerKeyMap:
    """Tests verifying _TRIGGER_KEY_MAP in unified_evaluator."""

    def test_trigger_key_map_exists(self) -> None:
        """unified_evaluator exports _TRIGGER_KEY_MAP."""
        import gobby.workflows.unified_evaluator as ue_module

        assert hasattr(ue_module, "_TRIGGER_KEY_MAP"), (
            "unified_evaluator should export _TRIGGER_KEY_MAP"
        )

    def test_trigger_key_map_resolves_common_event_types(self) -> None:
        """_TRIGGER_KEY_MAP correctly resolves common hook event types."""
        from gobby.workflows.unified_evaluator import _TRIGGER_KEY_MAP

        assert _TRIGGER_KEY_MAP[HookEventType.SESSION_START] == "on_session_start"
        assert _TRIGGER_KEY_MAP[HookEventType.SESSION_END] == "on_session_end"
        assert _TRIGGER_KEY_MAP[HookEventType.BEFORE_TOOL] == "on_before_tool"
        assert _TRIGGER_KEY_MAP[HookEventType.AFTER_TOOL] == "on_after_tool"
        assert _TRIGGER_KEY_MAP[HookEventType.BEFORE_AGENT] == "on_before_agent"
        assert _TRIGGER_KEY_MAP[HookEventType.AFTER_AGENT] == "on_after_agent"
        assert _TRIGGER_KEY_MAP[HookEventType.STOP] == "on_stop"
        assert _TRIGGER_KEY_MAP[HookEventType.PRE_COMPACT] == "on_pre_compact"
