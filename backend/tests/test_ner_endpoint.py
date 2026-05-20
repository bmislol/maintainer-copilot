"""Unit tests for the modelserver NER endpoint.

These tests stub the pipeline so they don't require downloading the 400MB
NER model. They verify the response-shape contract.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def stub_modelserver():
    """A modelserver app with the NER pipeline stubbed out."""
    from app.modelserver import app

    fake_ner = MagicMock()
    fake_ner.return_value = [
        {
            "entity_group": "ORG",
            "word": "sklearn",
            "start": 0,
            "end": 7,
            "score": 0.99,
        },
        {
            "entity_group": "MISC",
            "word": "1.4.0",
            "start": 12,
            "end": 17,
            "score": 0.87,
        },
    ]

    app.state.ner = fake_ner
    return TestClient(app)


def test_ner_returns_entities_with_correct_shape(stub_modelserver):
    response = stub_modelserver.post(
        "/ner",
        json={"text": "sklearn at 1.4.0 has a bug in RandomForestClassifier"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "entities" in body
    assert len(body["entities"]) == 2
    e0 = body["entities"][0]
    assert e0["label"] == "ORG"
    assert e0["text"] == "sklearn"
    assert 0.0 <= e0["score"] <= 1.0


def test_ner_rejects_empty_text(stub_modelserver):
    response = stub_modelserver.post("/ner", json={"text": ""})
    assert response.status_code == 422  # pydantic min_length validation


def test_ner_rejects_oversized_text(stub_modelserver):
    response = stub_modelserver.post("/ner", json={"text": "x" * 6000})
    assert response.status_code == 422
