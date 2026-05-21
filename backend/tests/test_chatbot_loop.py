"""Tests for the tool-calling loop — Phase 4.2.

Mocks the Anthropic async client to avoid live API calls.
Verifies the loop terminates correctly on end_turn and tool_use→result→end_turn.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock

from app.chatbot.loop import MAX_ROUNDS, run_stream


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


@pytest.mark.asyncio
async def test_loop_end_turn_yields_text() -> None:
    end_msg = _make_message("end_turn", [_text_block("Hello, maintainer!")])

    ctx = _make_stream_context(end_msg)
    anthropic = MagicMock()
    anthropic.messages.stream.return_value = ctx

    chunks = []
    async for chunk in run_stream(
        system_prompt="sys",
        user_message="hi",
        anthropic_client=anthropic,
        http_client=AsyncMock(),
        session=AsyncMock(),
    ):
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
            system_prompt="sys",
            user_message="classify this",
            anthropic_client=anthropic,
            http_client=AsyncMock(),
            session=AsyncMock(),
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
            system_prompt="sys",
            user_message="keep calling tools",
            anthropic_client=anthropic,
            http_client=AsyncMock(),
            session=AsyncMock(),
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

    # Return tool_use for rounds 1..MAX_ROUNDS-1, then end_turn
    call_count = 0

    def _side_effect(**kwargs: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        tools_arg = kwargs.get("tools", [])
        if call_count == MAX_ROUNDS:
            # On the last round, tools must be empty
            assert tools_arg == [], f"expected no tools on final round, got {tools_arg}"
            return _make_stream_context(end_msg)
        return _make_stream_context(tool_msg)

    anthropic = MagicMock()
    anthropic.messages.stream.side_effect = _side_effect

    with patch("app.chatbot.loop.execute_tool", new=AsyncMock(return_value={"label": "bug"})):
        chunks = []
        async for chunk in run_stream(
            system_prompt="sys",
            user_message="x",
            anthropic_client=anthropic,
            http_client=AsyncMock(),
            session=AsyncMock(),
        ):
            chunks.append(chunk)

    assert chunks == ["done"]
