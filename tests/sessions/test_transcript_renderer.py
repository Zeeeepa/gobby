from datetime import UTC, datetime

import pytest

from gobby.sessions.transcript_renderer import RenderState, render_incremental, render_transcript
from gobby.sessions.transcripts.base import ParsedMessage


def make_msg(
    index,
    role,
    content,
    content_type="text",
    tool_use_id=None,
    tool_name=None,
    tool_input=None,
    tool_result=None,
):
    return ParsedMessage(
        index=index,
        role=role,
        content=content,
        content_type=content_type,
        tool_name=tool_name,
        tool_input=tool_input,
        tool_result=tool_result,
        timestamp=datetime.now(UTC),
        raw_json={},
        tool_use_id=tool_use_id,
    )


def test_render_transcript_groups_assistant_text():
    msgs = [
        make_msg(0, "user", "hello"),
        make_msg(1, "assistant", "Hi "),
        make_msg(2, "assistant", "there!"),
    ]
    rendered = render_transcript(msgs)
    assert len(rendered) == 2
    assert rendered[0].role == "user"
    assert rendered[0].content == "hello"
    assert rendered[1].role == "assistant"
    assert rendered[1].content == "Hi there!"
    assert len(rendered[1].content_blocks) == 1
    assert rendered[1].content_blocks[0].content == "Hi there!"


def test_render_transcript_pairs_tool_results():
    msgs = [
        make_msg(
            0,
            "assistant",
            "",
            content_type="tool_use",
            tool_use_id="call-1",
            tool_name="mcp__test__tool",
            tool_input={"a": 1},
        ),
        make_msg(
            1,
            "user",
            "Result here",
            content_type="tool_result",
            tool_use_id="call-1",
            tool_result={"out": "ok"},
        ),
    ]
    rendered = render_transcript(msgs)
    # Both should be in ONE assistant message because tool_result is paired
    assert len(rendered) == 1
    assert rendered[0].role == "assistant"
    assert len(rendered[0].content_blocks) == 1
    block = rendered[0].content_blocks[0]
    assert block.type == "tool_chain"
    assert block.tool_calls[0].id == "call-1"
    assert block.tool_calls[0].result is not None
    assert block.tool_calls[0].result.content == {"out": "ok"}


def test_render_transcript_deduplicates_streaming_content():
    msgs = [
        make_msg(0, "assistant", "Hello"),
        make_msg(1, "assistant", "Hello"),  # Duplicate
        make_msg(2, "assistant", " World"),
    ]
    rendered = render_transcript(msgs)
    assert len(rendered) == 1
    assert rendered[0].content == "Hello World"


def test_render_transcript_classifies_hook_feedback_as_system():
    msgs = [
        make_msg(0, "user", "Stop hook feedback: something happened"),
    ]
    rendered = render_transcript(msgs)
    assert len(rendered) == 1
    assert rendered[0].role == "system"


def test_render_transcript_strips_hook_context_from_user():
    msgs = [
        make_msg(0, "user", "hello <hook_context>some metadata</hook_context>"),
    ]
    rendered = render_transcript(msgs)
    assert len(rendered) == 1
    assert rendered[0].content == "hello"


def test_render_incremental_returns_completed_turns():
    state = RenderState()

    # Turn 1: User
    completed, state = render_incremental([make_msg(0, "user", "hi")], state)
    assert len(completed) == 0  # User turn not finished until next turn starts or transcript ends

    # Turn 2: Assistant starts
    completed, state = render_incremental([make_msg(1, "assistant", "Hello")], state)
    assert len(completed) == 1
    assert completed[0].role == "user"

    # Turn 2: Assistant continues
    completed, state = render_incremental([make_msg(2, "assistant", "!")], state)
    assert len(completed) == 0

    # Turn 3: User starts
    completed, state = render_incremental([make_msg(3, "user", "how are you")], state)
    assert len(completed) == 1
    assert completed[0].role == "assistant"
    assert completed[0].content == "Hello!"


def test_render_transcript_unknown_block_type():
    msg = make_msg(0, "assistant", "special", content_type="random_type")
    msg.raw_json = {"some": "raw"}
    
    rendered = render_transcript([msg])
    assert len(rendered) == 1
    block = rendered[0].content_blocks[0]
    assert block.type == "unknown"
    assert block.block_type == "random_type"
    assert block.raw == {"some": "raw"}


def test_render_transcript_web_search_result():
    msg = make_msg(
        0,
        "assistant",
        "search results",
        content_type="web_search_tool_result",
        tool_result={"results": []},
    )
    rendered = render_transcript([msg])
    assert len(rendered) == 1
    block = rendered[0].content_blocks[0]
    assert block.type == "web_search_result"
    assert block.content == {"results": []}
