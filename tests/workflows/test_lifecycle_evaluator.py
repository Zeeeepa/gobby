"""Tests for unified evaluator delegation in lifecycle_evaluator.py."""

import pytest

from gobby.hooks.events import HookEventType

pytestmark = pytest.mark.unit


class TestUnifiedEvaluatorDelegation:
    """Tests verifying lifecycle_evaluator delegates to unified_evaluator."""

    def test_trigger_key_map_imported_from_unified_evaluator(self) -> None:
        """lifecycle_evaluator imports _TRIGGER_KEY_MAP from unified_evaluator."""
        import gobby.workflows.lifecycle_evaluator as le_module

        assert hasattr(le_module, "_TRIGGER_KEY_MAP"), (
            "lifecycle_evaluator should import _TRIGGER_KEY_MAP from unified_evaluator"
        )

    def test_trigger_key_map_identity(self) -> None:
        """Imported _TRIGGER_KEY_MAP is the same object as in unified_evaluator."""
        from gobby.workflows.lifecycle_evaluator import _TRIGGER_KEY_MAP
        from gobby.workflows.unified_evaluator import _TRIGGER_KEY_MAP as original_map

        assert _TRIGGER_KEY_MAP is original_map

    def test_trigger_key_map_resolves_common_event_types(self) -> None:
        """_TRIGGER_KEY_MAP correctly resolves common hook event types."""
        from gobby.workflows.lifecycle_evaluator import _TRIGGER_KEY_MAP

        assert _TRIGGER_KEY_MAP[HookEventType.SESSION_START] == "on_session_start"
        assert _TRIGGER_KEY_MAP[HookEventType.SESSION_END] == "on_session_end"
        assert _TRIGGER_KEY_MAP[HookEventType.BEFORE_TOOL] == "on_before_tool"
        assert _TRIGGER_KEY_MAP[HookEventType.AFTER_TOOL] == "on_after_tool"
        assert _TRIGGER_KEY_MAP[HookEventType.BEFORE_AGENT] == "on_before_agent"
        assert _TRIGGER_KEY_MAP[HookEventType.AFTER_AGENT] == "on_after_agent"
        assert _TRIGGER_KEY_MAP[HookEventType.STOP] == "on_stop"
        assert _TRIGGER_KEY_MAP[HookEventType.PRE_COMPACT] == "on_pre_compact"
