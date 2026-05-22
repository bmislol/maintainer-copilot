"""Thin wrapper around the backend API for the Streamlit admin app."""

from __future__ import annotations

import os
from collections.abc import Iterator

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")


def login(email: str, password: str) -> str:
    """POST /auth/jwt/login — returns JWT on success, raises HTTPError on failure."""
    resp = requests.post(
        f"{API_URL}/auth/jwt/login",
        data={"username": email, "password": password},
        timeout=10,
    )
    resp.raise_for_status()
    return str(resp.json()["access_token"])


def send_message_stream(
    token: str,
    message: str,
    conversation_id: str | None,
) -> Iterator[str]:
    """POST /chat/send — yields text chunks from the SSE stream.

    Parses `data: <chunk>` lines, stops on `data: [DONE]`.
    """
    resp = requests.post(
        f"{API_URL}/chat/send",
        json={"conversation_id": conversation_id, "message": message},
        headers={"Authorization": f"Bearer {token}"},
        stream=True,
        timeout=120,
    )
    resp.raise_for_status()
    for raw_line in resp.iter_lines():
        line: str = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if line.startswith("data: "):
            chunk = line[6:]
            if chunk == "[DONE]":
                return
            yield chunk


def get_memory_entries(token: str) -> list[dict]:  # type: ignore[type-arg]
    """GET /memory/entries — returns list of memory entry dicts."""
    resp = requests.get(
        f"{API_URL}/memory/entries",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return list(resp.json())


def create_widget(
    token: str,
    *,
    name: str,
    theme: str,
    greeting: str,
    enabled_tools: list[str],
    allowed_origins: list[str],
) -> dict:  # type: ignore[type-arg]
    """POST /widgets/ — creates a widget, returns the full widget dict."""
    resp = requests.post(
        f"{API_URL}/widgets/",
        json={
            "name": name,
            "theme": theme,
            "greeting": greeting,
            "enabled_tools": enabled_tools,
            "allowed_origins": allowed_origins,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return dict(resp.json())


def update_widget(
    token: str,
    widget_id: str,
    *,
    patch: dict,  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    """PATCH /widgets/{id} — updates a widget, returns the updated widget dict."""
    resp = requests.patch(
        f"{API_URL}/widgets/{widget_id}",
        json=patch,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return dict(resp.json())


def get_my_widgets(token: str) -> list[dict]:  # type: ignore[type-arg]
    """GET /widgets/mine — returns all widgets owned by the calling user."""
    resp = requests.get(
        f"{API_URL}/widgets/mine",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return list(resp.json())
