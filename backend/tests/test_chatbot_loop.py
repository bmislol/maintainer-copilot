"""Tests for the tool-calling loop — Phase 4.2 / updated Phase 4.3.

Mocks the Anthropic async client and Redis client to avoid live API calls.
Verifies the loop terminates correctly on end_turn and tool_use→result→end_turn.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock

from app.chatbot.loop import MAX_ROUNDS, run_stream

_CONV_ID = "test-conv-id"
_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")


def _make_message(stop_reason: str, content: list[Any]) -> Message:
    msg = MagicMock(spec=Message)
    msg.stop_reason = stop_reason
    msg.content = content
    return msg


def _text_block(text: str) -> TextBlock:
    block = MagicMock(spec=TextBlock)
    block.text = text
    return block


def _tool_use_block(name: str, tool_id: str, input_data: dict[str, Any]) -> ToolUseBlock:
    block = MagicMock(spec=ToolUseBlock)
    block.name = name
    block.id = tool_id
    block.input = input_data
    return block


def _make_stream_context(message: Message) -> MagicMock:
    """Return a sync callable that produces an async context manager."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=ctx)
    ctx.__aexit__ = AsyncMock(return_value=False)
    ctx.get_final_message = AsyncMock(return_value=message)
    return ctx


def _mock_redis() -> MagicMock:
    """Return a mock Redis client that returns empty history."""
    redis = MagicMock()
    redis.lrange = AsyncMock(return_value=[])
    pipe = MagicMock()
    pipe.rpush = MagicMock(return_value=pipe)
    pipe.ltrim = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[1, None, True])
    redis.pipeline = MagicMock(return_value=pipe)
    return redis


def _run_stream_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "system_prompt": "sys",
        "user_message": "hi",
        "conversation_id": _CONV_ID,
        "anthropic_client": MagicMock(),
        "http_client": AsyncMock(),
        "session": AsyncMock(),
        "redis_client": _mock_redis(),
        "user_id": _USER_ID,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_loop_end_turn_yields_text() -> None:
    end_msg = _make_message("end_turn", [_text_block("Hello, maintainer!")])

    ctx = _make_stream_context(end_msg)
    anthropic = MagicMock()
    anthropic.messages.stream.return_value = ctx

    chunks = []
    async for chunk in run_stream(**_run_stream_kwargs(anthropic_client=anthropic)):
        chunks.append(chunk)

    assert chunks == ["Hello, maintainer!"]
    assert anthropic.messages.stream.call_count == 1


@pytest.mark.asyncio
async def test_loop_tool_use_then_end_turn() -> None:
    tool_msg = _make_message(
        "tool_use",
        [_tool_use_block("classify_issue", "tu_1", {"text": "bug report"})],
    )
    end_msg = _make_message("end_turn", [_text_block("It's a bug.")])

    call_count = 0

    def _stream_side_effect(**_kwargs: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        return _make_stream_context(tool_msg if call_count == 1 else end_msg)

    anthropic = MagicMock()
    anthropic.messages.stream.side_effect = _stream_side_effect

    with patch(
        "app.chatbot.loop.execute_tool",
        new=AsyncMock(return_value={"label": "bug", "confidence": 0.95}),
    ):
        chunks = []
        async for chunk in run_stream(
            **_run_stream_kwargs(anthropic_client=anthropic, user_message="classify this")
        ):
            chunks.append(chunk)

    assert chunks == ["It's a bug."]
    assert anthropic.messages.stream.call_count == 2


@pytest.mark.asyncio
async def test_loop_exhausts_rounds_and_yields_fallback() -> None:
    tool_msg = _make_message(
        "tool_use",
        [_tool_use_block("classify_issue", "tu_x", {"text": "x"})],
    )

    ctx = _make_stream_context(tool_msg)
    anthropic = MagicMock()
    anthropic.messages.stream.return_value = ctx

    with patch(
        "app.chatbot.loop.execute_tool",
        new=AsyncMock(return_value={"label": "bug"}),
    ):
        chunks = []
        async for chunk in run_stream(
            **_run_stream_kwargs(anthropic_client=anthropic, user_message="keep calling tools")
        ):
            chunks.append(chunk)

    assert len(chunks) == 1
    assert "max tool rounds" in chunks[0]
    assert anthropic.messages.stream.call_count == MAX_ROUNDS


@pytest.mark.asyncio
async def test_last_round_sends_no_tools() -> None:
    """On the final round, TOOL_SCHEMAS must be empty so Claude can't call more tools."""
    end_msg = _make_message("end_turn", [_text_block("done")])
    tool_msg = _make_message(
        "tool_use",
        [_tool_use_block("classify_issue", "tu_1", {"text": "x"})],
    )

    call_count = 0

    def _side_effect(**kwargs: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        tools_arg = kwargs.get("tools", [])
        if call_count == MAX_ROUNDS:
            assert tools_arg == [], f"expected no tools on final round, got {tools_arg}"
            return _make_stream_context(end_msg)
        return _make_stream_context(tool_msg)

    anthropic = MagicMock()
    anthropic.messages.stream.side_effect = _side_effect

    with patch("app.chatbot.loop.execute_tool", new=AsyncMock(return_value={"label": "bug"})):
        chunks = []
        async for chunk in run_stream(**_run_stream_kwargs(anthropic_client=anthropic)):
            chunks.append(chunk)

    assert chunks == ["done"]


@pytest.mark.asyncio
async def test_loop_loads_history_from_redis() -> None:
    """History from Redis is prepended to the messages array sent to Claude."""
    end_msg = _make_message("end_turn", [_text_block("Sure!")])

    ctx = _make_stream_context(end_msg)
    anthropic = MagicMock()
    anthropic.messages.stream.return_value = ctx

    redis = _mock_redis()
    redis.lrange = AsyncMock(return_value=['{"role": "user", "content": "prior msg"}'])

    chunks = []
    async for chunk in run_stream(
        **_run_stream_kwargs(
            anthropic_client=anthropic,
            redis_client=redis,
            user_message="follow-up",
        )
    ):
        chunks.append(chunk)

    call_kwargs = anthropic.messages.stream.call_args.kwargs
    messages_sent = call_kwargs["messages"]
    # First message should be the history entry, last should be the new user message
    assert messages_sent[0] == {"role": "user", "content": "prior msg"}
    assert messages_sent[-1] == {"role": "user", "content": "follow-up"}
