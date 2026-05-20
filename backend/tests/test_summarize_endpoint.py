"""Unit tests for the modelserver summarize endpoint.

These tests stub the Anthropic client so they don't require API credits.
They verify the request/response contract.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def stub_modelserver():
    """A modelserver app with the summarizer Anthropic client stubbed out."""
    from app.modelserver import app

    fake_text_block = MagicMock()
    fake_text_block.type = "text"
    fake_text_block.text = (
        "User reports that sklearn 1.4 fails to fit RandomForest with sparse inputs."
    )

    fake_response = MagicMock()
    fake_response.content = [fake_text_block]

    fake_client = MagicMock()
    fake_client.messages = MagicMock()
    fake_client.messages.create = AsyncMock(return_value=fake_response)

    app.state.summarizer = fake_client
    return TestClient(app)


def test_summarize_returns_summary_with_correct_shape(stub_modelserver):
    issue_body = (
        "I tried fitting RandomForestClassifier with sparse CSR input and got a "
        "ValueError about array conversion. This used to work in sklearn 1.3 but "
        "stopped working in 1.4. I tested with both CSR and CSC formats. The error "
        "trace shows the conversion happens deep in the tree building code. "
        "Has the API changed?"
    )
    response = stub_modelserver.post("/summarize", json={"text": issue_body})
    assert response.status_code == 200
    body = response.json()
    assert "summary" in body
    assert isinstance(body["summary"], str)
    assert len(body["summary"]) > 0
    assert body["original_chars"] == len(issue_body)
    assert body["summary_chars"] == len(body["summary"])
    assert body["model"] == "claude-haiku-4-5"


def test_summarize_rejects_too_short_text(stub_modelserver):
    response = stub_modelserver.post("/summarize", json={"text": "short"})
    assert response.status_code == 422


def test_summarize_rejects_oversized_text(stub_modelserver):
    response = stub_modelserver.post("/summarize", json={"text": "x" * 11000})
    assert response.status_code == 422
