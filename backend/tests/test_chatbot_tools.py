"""Tests for chatbot tool executors — Phase 4.2.

Uses a mock httpx.AsyncClient and mock AsyncSession to avoid live
infrastructure. Verifies the executor contract: returns a JSON-serialisable
dict on success, and {"error": "..."} on failure.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.chatbot.tools import (
    execute_classify_issue,
    execute_extract_entities,
    execute_retrieve_docs,
    execute_summarize_thread,
    execute_tool,
    execute_write_memory,
)


def _mock_http(json_payload: dict[str, Any], status_code: int = 200) -> AsyncMock:
    """Return a mock httpx.AsyncClient whose POST returns json_payload."""
    resp = MagicMock()
    resp.json.return_value = json_payload
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from httpx import HTTPStatusError, Request, Response

        resp.raise_for_status.side_effect = HTTPStatusError(
            "error", request=MagicMock(spec=Request), response=MagicMock(spec=Response)
        )
    client = AsyncMock()
    client.post = AsyncMock(return_value=resp)
    return client


@pytest.mark.asyncio
async def test_classify_issue_returns_label_and_confidence() -> None:
    http = _mock_http({"label": "bug", "confidence": 0.91})
    result = await execute_classify_issue({"text": "Something broke"}, http_client=http)
    assert result == {"label": "bug", "confidence": 0.91}
    http.post.assert_awaited_once_with("/classify", json={"text": "Something broke"})


@pytest.mark.asyncio
async def test_classify_issue_returns_error_on_http_failure() -> None:
    http = _mock_http({}, status_code=500)
    result = await execute_classify_issue({"text": "x"}, http_client=http)
    assert "error" in result
    assert "classify_issue unavailable" in result["error"]


@pytest.mark.asyncio
async def test_extract_entities_returns_entities_list() -> None:
    http = _mock_http({"entities": [{"text": "fit_transform", "label": "FUNC"}]})
    result = await execute_extract_entities({"text": "call fit_transform"}, http_client=http)
    assert result == {"entities": [{"text": "fit_transform", "label": "FUNC"}]}


@pytest.mark.asyncio
async def test_extract_entities_returns_error_on_failure() -> None:
    http = _mock_http({}, status_code=503)
    result = await execute_extract_entities({"text": "x"}, http_client=http)
    assert "error" in result


@pytest.mark.asyncio
async def test_summarize_thread_returns_summary() -> None:
    http = _mock_http({"summary": "Short summary."})
    result = await execute_summarize_thread({"text": "long thread..."}, http_client=http)
    assert result == {"summary": "Short summary."}


@pytest.mark.asyncio
async def test_summarize_thread_returns_error_on_failure() -> None:
    http = _mock_http({}, status_code=500)
    result = await execute_summarize_thread({"text": "x"}, http_client=http)
    assert "error" in result


@pytest.mark.asyncio
async def test_write_memory_stub_returns_ok() -> None:
    result = await execute_write_memory({"content": "remember this"})
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_execute_tool_unknown_name_returns_error() -> None:
    result = await execute_tool(
        "does_not_exist",
        {},
        http_client=AsyncMock(),
        session=AsyncMock(),
        anthropic_client=AsyncMock(),
    )
    assert result == {"error": "unknown tool: does_not_exist"}


@pytest.mark.asyncio
async def test_retrieve_docs_returns_chunks() -> None:
    mock_chunk = MagicMock()
    mock_chunk.chunk_id = "abc123"
    mock_chunk.source_type = "docs"
    mock_chunk.text = "relevant documentation text"

    mock_pipeline = AsyncMock()
    mock_pipeline.run = AsyncMock(return_value=[mock_chunk])

    with patch("app.rag.pipeline.RAGPipeline", return_value=mock_pipeline):
        result = await execute_retrieve_docs(
            {"query": "how to fit", "source": "docs"},
            session=AsyncMock(),
            anthropic_client=AsyncMock(),
        )

    assert "chunks" in result
    assert result["chunks"][0]["chunk_id"] == "abc123"
    assert result["chunks"][0]["source_type"] == "docs"
