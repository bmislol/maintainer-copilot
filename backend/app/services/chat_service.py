"""Chat service — Phase 4.2.

Thin orchestration layer between the HTTP endpoint and the tool-calling loop.
Responsibilities:
  - Load the system prompt from disk (cached after first read).
  - Open a Langfuse span around the loop invocation.
  - Yield text delta strings from the loop for the endpoint to stream.

Layer: app/services/
Used by: app/api/chat.py
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from functools import lru_cache
from pathlib import Path

import httpx
from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.chatbot.loop import run_stream
from app.infra.tracing import get_client

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "system.md"


@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


async def stream_chat_response(
    *,
    user_message: str,
    conversation_id: str | None,
    anthropic_client: AsyncAnthropic,
    http_client: httpx.AsyncClient,
    session: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Yield text delta strings for one chatbot turn.

    Wraps the tool-calling loop in a Langfuse span when tracing is active.
    conversation_id is carried for Phase 4.3 persistence; unused here.
    """
    system_prompt = _load_system_prompt()
    langfuse = get_client()

    span = None
    if langfuse is not None:
        span = langfuse.span(
            name="chatbot_turn",
            input={"message": user_message, "conversation_id": conversation_id},
        )

    try:
        async for chunk in run_stream(
            system_prompt=system_prompt,
            user_message=user_message,
            anthropic_client=anthropic_client,
            http_client=http_client,
            session=session,
        ):
            yield chunk
    finally:
        if span is not None:
            span.end()
