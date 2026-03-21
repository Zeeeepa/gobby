"""Tests for MessageRouter."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gobby.communications.models import CommsRoutingRule
from gobby.communications.router import MessageRouter


@pytest.mark.asyncio
async def test_router_matching():
    # Mock store
    store = MagicMock()
    rules = [
        CommsRoutingRule(
            id="rule-1", name="Rule 1", channel_id="chan-1", event_pattern="task.*", priority=10
        ),
        CommsRoutingRule(
            id="rule-2", name="Rule 2", channel_id="chan-2", event_pattern="*", priority=0
        ),
        CommsRoutingRule(
            id="rule-3",
            name="Rule 3",
            channel_id="chan-3",
            event_pattern="session.started",
            priority=20,
        ),
        CommsRoutingRule(
            id="rule-disabled",
            name="Disabled Rule",
            channel_id="chan-4",
            event_pattern="*",
            priority=100,
            enabled=False,
        ),
    ]

    def get_rules(enabled_only=True):
        rs = [r for r in rules if not enabled_only or r.enabled]
        return sorted(rs, key=lambda x: x.priority, reverse=True)

    store.get_routing_rules.side_effect = get_rules

    router = MessageRouter(store)

    # Matches task.* and *
    matched = await router.match_channels("task.created")
    # Rule 1 (10) and Rule 2 (0) match. Rule 3 doesn't. Disabled doesn't.
    assert matched == ["chan-1", "chan-2"]

    # Matches session.started and *
    matched = await router.match_channels("session:started")  # Test normalization
    assert matched == ["chan-3", "chan-2"]

    # Matches only *
    matched = await router.match_channels("unknown.event")
    assert matched == ["chan-2"]


@pytest.mark.asyncio
async def test_router_filtering():
    store = MagicMock()
    rules = [
        CommsRoutingRule(
            id="rule-proj",
            name="Project Rule",
            channel_id="chan-proj",
            event_pattern="*",
            project_id="proj-1",
            priority=10,
        ),
        CommsRoutingRule(
            id="rule-sess",
            name="Session Rule",
            channel_id="chan-sess",
            event_pattern="*",
            session_id="sess-1",
            priority=5,
        ),
    ]
    store.get_routing_rules.return_value = rules

    router = MessageRouter(store)

    # Match project
    assert await router.match_channels("any", project_id="proj-1") == ["chan-proj"]
    # No project match
    assert await router.match_channels("any", project_id="proj-2") == []

    # Match session
    assert await router.match_channels("any", session_id="sess-1") == ["chan-sess"]
    # No session match
    assert await router.match_channels("any", session_id="sess-2") == []
