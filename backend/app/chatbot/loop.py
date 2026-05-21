"""Tool-calling loop — Phase 4.2.

Standard Anthropic tool-use pattern, capped at MAX_ROUNDS to prevent
runaway loops. Yields text delta strings as an async generator so the
caller can stream them directly to the SSE response.

Round budget (D-034): 5 rounds. In practice every tested query resolves in
1-2 rounds. The cap is a hard safety rail, not a normal operating ceiling.

Layer: app/chatbot/
Used by: app/services/chat_service.py
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from anthropic import AsyncAnthropic
from anthropic.types import Message, MessageParam, ToolUseBlock
from sqlalchemy.ext.asyncio import AsyncSession

from app.chatbot.tools import TOOL_SCHEMAS, execute_tool

logger = logging.getLogger(__name__)

MAX_ROUNDS = 5
MODEL = "claude-haiku-4-5"


async def run_stream(
    *,
    system_prompt: str,
    user_message: str,
    anthropic_client: AsyncAnthropic,
    http_client: httpx.AsyncClient,
    session: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Run the tool-calling loop and yield text delta strings.

    Yields individual text chunks as Claude produces them.
    Raises on unrecoverable Anthropic API errors.
    """
    messages: list[MessageParam] = [{"role": "user", "content": user_message}]

    for round_num in range(MAX_ROUNDS):
        logger.debug("chatbot loop round %d", round_num + 1)

        # ----------------------------------------------------------------
        # Check if this is the last round — if so, don't offer tools so
        # Claude is forced to give a text response rather than call more tools.
        # ----------------------------------------------------------------
        tools_for_this_round = TOOL_SCHEMAS if round_num < MAX_ROUNDS - 1 else []

        async with anthropic_client.messages.stream(
            model=MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
            tools=tools_for_this_round,  # type: ignore[arg-type]
        ) as stream:
            response: Message = await stream.get_final_message()

        # ----------------------------------------------------------------
        # Tool-use round: execute all tool calls, then loop back.
        # ----------------------------------------------------------------
        if response.stop_reason == "tool_use":
            # Append assistant's tool-use turn to the conversation.
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            # Execute every tool call in this response and collect results.
            tool_results: list[dict[str, Any]] = []
            for block in assistant_content:
                if not isinstance(block, ToolUseBlock):
                    continue
                logger.debug("executing tool %s (id=%s)", block.name, block.id)
                result = await execute_tool(
                    block.name,
                    dict(block.input),
                    http_client=http_client,
                    session=session,
                    anthropic_client=anthropic_client,
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    }
                )

            messages.append({"role": "user", "content": tool_results})  # type: ignore[typeddict-item]
            continue  # back to the top of the loop

        # ----------------------------------------------------------------
        # End-turn: stream the text response and exit.
        # ----------------------------------------------------------------
        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    # Yield the full text from this block; the endpoint
                    # wraps individual tokens in SSE events.
                    yield block.text
            return

        # Unexpected stop_reason — log and bail.
        logger.warning("unexpected stop_reason %r on round %d", response.stop_reason, round_num + 1)
        yield f"[unexpected stop reason: {response.stop_reason}]"
        return

    # Exhausted all rounds without end_turn.
    logger.warning("chatbot loop exhausted %d rounds without end_turn", MAX_ROUNDS)
    yield "[max tool rounds reached — please try rephrasing your question]"
