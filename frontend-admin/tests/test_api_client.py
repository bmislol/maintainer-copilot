"""Tests for the api_client wrapper — Phase 4.4."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from utils.api_client import get_memory_entries, login


def _mock_response(status_code: int, json_data: object) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


def test_login_returns_token_on_success() -> None:
    mock_resp = _mock_response(200, {"access_token": "tok123"})
    with patch("utils.api_client.requests.post", return_value=mock_resp) as mock_post:
        token = login("user@example.com", "secret")
    assert token == "tok123"
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["data"] == {"username": "user@example.com", "password": "secret"}


def test_login_raises_on_bad_credentials() -> None:
    mock_resp = _mock_response(400, {"detail": "LOGIN_BAD_CREDENTIALS"})
    with patch("utils.api_client.requests.post", return_value=mock_resp):
        with pytest.raises(requests.HTTPError):
            login("bad@example.com", "wrong")


def test_get_memory_entries_returns_list() -> None:
    entries = [
        {
            "id": "uuid1",
            "content": "check CI",
            "memory_type": "episodic",
            "created_at": "2026-01-01T00:00:00",
        }
    ]
    mock_resp = _mock_response(200, entries)
    with patch("utils.api_client.requests.get", return_value=mock_resp):
        result = get_memory_entries("tok123")
    assert result == entries


def test_get_memory_entries_raises_on_unauthorized() -> None:
    mock_resp = _mock_response(401, {"detail": "Unauthorized"})
    with patch("utils.api_client.requests.get", return_value=mock_resp):
        with pytest.raises(requests.HTTPError):
            get_memory_entries("bad-token")
