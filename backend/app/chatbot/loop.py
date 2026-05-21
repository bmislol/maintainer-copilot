"""Tool-calling loop — Phase 4.2 / updated Phase 4.3.

Standard Anthropic tool-use pattern, capped at MAX_ROUNDS to prevent
runaway loops. Yields text delta strings as an async generator so the
caller can stream them directly to the SSE response.

Round budget (D-034): 5 rounds. In practice every tested query resolves in
1-2 rounds. The cap is a hard safety rail, not a normal operating ceiling.

Phase 4.3 changes:
- Accepts conversation_id and redis_client so Redis history is loaded and
  written here (keeping HTTP concerns in the service layer above).
- Passes user_id / request_id / trace_id through to execute_tool so the
  write_memory executor can attribute long-term writes correctly.

Layer: app/chatbot/
Used by: app/services/chat_service.py
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from anthropic import AsyncAnthropic
from anthropic.types import Message, MessageParam, ToolUseBlock
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.chatbot.tools import TOOL_SCHEMAS, execute_tool
from app.memory.short_term import append_message, get_history

logger = logging.getLogger(__name__)

MAX_ROUNDS = 5
MODEL = "claude-haiku-4-5"


async def run_stream(
    *,
    system_prompt: str,
    user_message: str,
    conversation_id: str,
    anthropic_client: AsyncAnthropic,
    http_client: httpx.AsyncClient,
    session: AsyncSession,
    redis_client: Redis,
    user_id: uuid.UUID,
    request_id: str = "",
    trace_id: str = "",
) -> AsyncGenerator[str, None]:
    """Run the tool-calling loop and yield text delta strings.

    Loads conversation history from Redis at the start of each turn,
    appends the new user message, then writes the assistant response back
    to Redis once streaming completes.

    Yields individual text chunks as Claude produces them.
    Raises on unrecoverable Anthropic API errors.
    """
    # Load history and append the incoming user message.
    history = await get_history(redis_client, conversation_id)
    await append_message(redis_client, conversation_id, "user", user_message)

    # Build the messages array Claude will see: history + current user turn.
    messages: list[MessageParam] = [
        *history,  # type: ignore[list-item]
        {"role": "user", "content": user_message},
    ]

    full_response_parts: list[str] = []

    for round_num in range(MAX_ROUNDS):
        logger.debug("chatbot loop round %d", round_num + 1)

        # On the final round pass no tools so Claude is forced to end_turn.
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
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

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
                    user_id=user_id,
                    request_id=request_id,
                    trace_id=trace_id,
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    }
                )

            messages.append({"role": "user", "content": tool_results})  # type: ignore[typeddict-item]
            continue

        # ----------------------------------------------------------------
        # End-turn: yield text, persist to Redis, exit.
        # ----------------------------------------------------------------
        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    full_response_parts.append(block.text)
                    yield block.text

            full_response = "".join(full_response_parts)
            await append_message(redis_client, conversation_id, "assistant", full_response)
            return

        # Unexpected stop_reason — log and bail.
        logger.warning("unexpected stop_reason %r on round %d", response.stop_reason, round_num + 1)
        yield f"[unexpected stop reason: {response.stop_reason}]"
        return

    # Exhausted all rounds without end_turn.
    logger.warning("chatbot loop exhausted %d rounds without end_turn", MAX_ROUNDS)
    yield "[max tool rounds reached — please try rephrasing your question]"
