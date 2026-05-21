"""Tests for short-term (Redis) memory — Phase 4.3."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.memory.short_term import (
    _MAX_MESSAGES,
    _TTL_SECONDS,
    append_message,
    clear,
    get_history,
)


def _mock_redis() -> MagicMock:
    redis = MagicMock()
    pipe = MagicMock()
    # Pipeline command methods are sync (they queue commands, not execute them)
    pipe.rpush = MagicMock(return_value=pipe)
    pipe.ltrim = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[1, None, True])
    redis.pipeline = MagicMock(return_value=pipe)
    redis.lrange = AsyncMock(return_value=[])
    redis.delete = AsyncMock(return_value=1)
    return redis


@pytest.mark.asyncio
async def test_append_message_uses_pipeline() -> None:
    redis = _mock_redis()
    await append_message(redis, "conv-1", "user", "hello")
    pipe = redis.pipeline.return_value
    pipe.rpush.assert_called_once()
    pipe.ltrim.assert_called_once()
    pipe.expire.assert_called_once()
    pipe.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_append_message_sets_correct_ttl() -> None:
    redis = _mock_redis()
    await append_message(redis, "conv-1", "user", "hello")
    pipe = redis.pipeline.return_value
    _, expire_args, _ = pipe.expire.mock_calls[0]
    assert expire_args[1] == _TTL_SECONDS


@pytest.mark.asyncio
async def test_append_message_trims_to_max_window() -> None:
    redis = _mock_redis()
    await append_message(redis, "conv-1", "user", "hello")
    pipe = redis.pipeline.return_value
    _, ltrim_args, _ = pipe.ltrim.mock_calls[0]
    # ltrim(key, -MAX_MESSAGES, -1)
    assert ltrim_args[1] == -_MAX_MESSAGES
    assert ltrim_args[2] == -1


@pytest.mark.asyncio
async def test_get_history_returns_parsed_messages() -> None:
    redis = _mock_redis()
    redis.lrange = AsyncMock(
        return_value=[
            '{"role": "user", "content": "hi"}',
            '{"role": "assistant", "content": "hello"}',
        ]
    )
    history = await get_history(redis, "conv-1")
    assert history == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    redis.lrange.assert_awaited_once_with("conv:conv-1:messages", 0, -1)


@pytest.mark.asyncio
async def test_get_history_returns_empty_list_for_new_conversation() -> None:
    redis = _mock_redis()
    history = await get_history(redis, "brand-new")
    assert history == []


@pytest.mark.asyncio
async def test_clear_deletes_key() -> None:
    redis = _mock_redis()
    await clear(redis, "conv-1")
    redis.delete.assert_awaited_once_with("conv:conv-1:messages")
