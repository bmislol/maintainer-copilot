"""Chat API router — Phase 4.2 / updated Phase 4.3.

Single endpoint: POST /chat/send
Streams the chatbot response as Server-Sent Events.

Layer: app/api/
Used by: app/main.py
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.db.models.users import User
from app.db.session import get_async_session
from app.infra.auth import get_current_user_or_widget
from app.services.chat_service import stream_chat_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str


@router.post("/send")
async def send_message(
    body: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user_or_widget),
    session: Any = Depends(get_async_session),
) -> EventSourceResponse:
    """Stream a chatbot response as SSE events.

    Each event carries a text delta. A final ``data: [DONE]`` event signals
    the stream is complete.
    """
    anthropic_client = request.app.state.anthropic_client
    http_client = request.app.state.http_client
    redis_client = request.app.state.redis_client
    request_id: str = getattr(request.state, "request_id", "")
    trace_id: str = getattr(request.state, "trace_id", "")

    async def event_generator() -> AsyncGenerator[str, None]:
        async for chunk in stream_chat_response(
            user_message=body.message,
            conversation_id=str(body.conversation_id) if body.conversation_id else None,
            user_id=user.id,
            anthropic_client=anthropic_client,
            http_client=http_client,
            session=session,
            redis_client=redis_client,
            request_id=request_id,
            trace_id=trace_id,
        ):
            yield chunk
        yield "[DONE]"

    return EventSourceResponse(event_generator())
