"""Short-term (Redis) conversation memory — Phase 4.3.

Per-conversation message history with a 24-hour TTL and a 50-message
sliding window. See D-023 for TTL and window-size rationale.

Key pattern: conv:{conversation_id}:messages
Each list element is a JSON-serialised {"role": ..., "content": ...} dict.

Layer: app/memory/
Dependencies flow IN — the Redis client is injected rather than imported
from app.state so this module stays testable without live infrastructure.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_TTL_SECONDS = 86_400  # 24 hours (D-023)
_MAX_MESSAGES = 50  # sliding window — oldest dropped when exceeded


def _key(conversation_id: str) -> str:
    return f"conv:{conversation_id}:messages"


async def append_message(
    redis: Redis,
    conversation_id: str,
    role: str,
    content: str,
) -> None:
    """Append one message to the conversation list, trim to window, refresh TTL."""
    k = _key(conversation_id)
    payload = json.dumps({"role": role, "content": content})
    pipe = redis.pipeline()
    pipe.rpush(k, payload)
    pipe.ltrim(k, -_MAX_MESSAGES, -1)
    pipe.expire(k, _TTL_SECONDS)
    await pipe.execute()


async def get_history(
    redis: Redis,
    conversation_id: str,
) -> list[dict[str, Any]]:
    """Return the full message list for a conversation (oldest first)."""
    raw: list[str] = await redis.lrange(_key(conversation_id), 0, -1)  # type: ignore[misc]
    return [json.loads(item) for item in raw]


async def clear(redis: Redis, conversation_id: str) -> None:
    """Delete the conversation history key."""
    await redis.delete(_key(conversation_id))
