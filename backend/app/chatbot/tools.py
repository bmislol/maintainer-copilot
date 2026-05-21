"""Tool definitions and executor functions — Phase 4.2.

Each tool has:
  - A JSON schema dict (``TOOL_SCHEMAS``) passed to the Anthropic API.
  - An async executor function that receives the tool input dict and the
    shared request-scoped dependencies (httpx client, DB session,
    Anthropic client).

Executor contract
-----------------
  - Return a JSON-serialisable dict on success.
  - On any exception, return ``{"error": "<tool_name> unavailable: <reason>"}``.
    Claude will relay the failure to the user gracefully rather than raising.

Layer: app/chatbot/
Dependencies flow IN from the loop (not imported at module level) to keep
this module testable without live infrastructure.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

_ExecutorFn = Callable[..., Coroutine[Any, Any, dict[str, Any]]]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool JSON schemas (passed verbatim to the Anthropic messages API)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "classify_issue",
        "description": (
            "Classify a GitHub issue into one of: bug, feature, docs, question. "
            "Returns the predicted label and a confidence score."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The issue title and body to classify.",
                }
            },
            "required": ["text"],
        },
    },
    {
        "name": "extract_entities",
        "description": (
            "Extract named entities from issue text: function names, file paths, "
            "error codes, version strings, and similar code-shaped tokens."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The issue text to extract entities from.",
                }
            },
            "required": ["text"],
        },
    },
    {
        "name": "summarize_thread",
        "description": (
            "Summarize a long issue thread into a short paragraph. "
            "Useful when the issue body is too long to read in full."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The full issue thread text to summarize.",
                }
            },
            "required": ["text"],
        },
    },
    {
        "name": "retrieve_docs",
        "description": (
            "Search the project documentation and resolved issues for content "
            "relevant to a query. Returns the top-5 most relevant chunks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
                "source": {
                    "type": "string",
                    "enum": ["docs", "issues", "all"],
                    "description": "Restrict to docs, issues, or search both.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "write_memory",
        "description": (
            "Save a fact or note to long-term memory so it can be recalled in future conversations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The text to remember.",
                }
            },
            "required": ["content"],
        },
    },
]


# ---------------------------------------------------------------------------
# Executor functions
# ---------------------------------------------------------------------------


async def execute_classify_issue(
    tool_input: dict[str, Any],
    *,
    http_client: httpx.AsyncClient,
    **_kwargs: Any,
) -> dict[str, Any]:
    try:
        resp = await http_client.post("/classify", json={"text": tool_input["text"]})
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return {"label": data["label"], "confidence": data["confidence"]}
    except Exception as exc:
        logger.warning("classify_issue failed: %s", exc)
        return {"error": f"classify_issue unavailable: {exc}"}


async def execute_extract_entities(
    tool_input: dict[str, Any],
    *,
    http_client: httpx.AsyncClient,
    **_kwargs: Any,
) -> dict[str, Any]:
    try:
        resp = await http_client.post("/ner", json={"text": tool_input["text"]})
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return {"entities": data.get("entities", [])}
    except Exception as exc:
        logger.warning("extract_entities failed: %s", exc)
        return {"error": f"extract_entities unavailable: {exc}"}


async def execute_summarize_thread(
    tool_input: dict[str, Any],
    *,
    http_client: httpx.AsyncClient,
    **_kwargs: Any,
) -> dict[str, Any]:
    try:
        resp = await http_client.post("/summarize", json={"text": tool_input["text"]})
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return {"summary": data["summary"]}
    except Exception as exc:
        logger.warning("summarize_thread failed: %s", exc)
        return {"error": f"summarize_thread unavailable: {exc}"}


async def execute_retrieve_docs(
    tool_input: dict[str, Any],
    *,
    session: AsyncSession,
    anthropic_client: AsyncAnthropic,
    **_kwargs: Any,
) -> dict[str, Any]:
    from app.rag.pipeline import RAGPipeline

    try:
        source = tool_input.get("source", "all")
        pipeline = RAGPipeline(
            session=session,
            anthropic_client=anthropic_client,
            top_k=5,
            source_filter=source,
        )
        chunks = await pipeline.run(tool_input["query"])
        return {
            "chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "source_type": c.source_type,
                    "text": c.text[:500],  # trim very long chunks for the context window
                }
                for c in chunks
            ]
        }
    except Exception as exc:
        logger.warning("retrieve_docs failed: %s", exc)
        return {"error": f"retrieve_docs unavailable: {exc}"}


async def execute_write_memory(
    tool_input: dict[str, Any],
    *,
    session: AsyncSession,
    user_id: uuid.UUID,
    request_id: str = "",
    trace_id: str = "",
    **_kwargs: Any,
) -> dict[str, Any]:
    from app.memory.long_term import write_entry

    try:
        entry = await write_entry(
            session,
            user_id=user_id,
            content=tool_input["content"],
            request_id=request_id,
            trace_id=trace_id,
        )
        return {"status": "ok", "entry_id": str(entry.id)}
    except Exception as exc:
        logger.warning("write_memory failed: %s", exc)
        return {"error": f"write_memory unavailable: {exc}"}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_EXECUTORS: dict[str, _ExecutorFn] = {
    "classify_issue": execute_classify_issue,
    "extract_entities": execute_extract_entities,
    "summarize_thread": execute_summarize_thread,
    "retrieve_docs": execute_retrieve_docs,
    "write_memory": execute_write_memory,
}


async def execute_tool(
    name: str,
    tool_input: dict[str, Any],
    *,
    http_client: httpx.AsyncClient,
    session: AsyncSession,
    anthropic_client: AsyncAnthropic,
    user_id: uuid.UUID | None = None,
    request_id: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    """Dispatch a tool call by name. Always returns a JSON-serialisable dict."""
    executor = _EXECUTORS.get(name)
    if executor is None:
        return {"error": f"unknown tool: {name}"}
    return await executor(
        tool_input,
        http_client=http_client,
        session=session,
        anthropic_client=anthropic_client,
        user_id=user_id,
        request_id=request_id,
        trace_id=trace_id,
    )
