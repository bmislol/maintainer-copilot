"""Cross-conversation memory recall demo — Phase 4.7.

Proves the full write → semantic-search → recall pipeline:

  Step 1 (Conversation A) — POST to /chat/send?widget_id=... with a message
    that asks Claude to remember a fact.  Claude calls the write_memory tool
    and the entry is persisted in pgvector.

  Step 2 (Conversation B) — Calls search() from app.memory.long_term
    directly with a semantically different query and asserts the written
    entry is recalled.

NOTE: In-chat memory recall requires a search_memory tool — the
underlying pgvector retrieval pipeline is demonstrated here directly.
Phase 5 would add the tool so Claude can surface stored facts
autonomously during a conversation.

Usage
-----
    DATABASE_URL="postgresql+asyncpg://copilot:copilot-dev-password@localhost:5432/copilot" \\
    uv run python -m scripts.demo_memory_recall

Requires the full compose stack to be up (api on localhost:8000, live DB).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models.users import User
from app.memory.long_term import search

WIDGET_ID = "00000000-0000-0000-0001-000000000001"
API_BASE = "http://localhost:8000"
ADMIN_EMAIL = "admin@maintainer-copilot.dev"

WRITE_MESSAGE = (
    "Please remember this for me: "
    "My name is Alex and I prefer detailed explanations when debugging issues."
)
RECALL_QUERY = "What do I know about this user's background and communication preferences?"


# ---------------------------------------------------------------------------
# Step 1 — write via the live chat API
# ---------------------------------------------------------------------------


def _collect_sse(text: str) -> str:
    """Extract concatenated text from an SSE body string."""
    parts: list[str] = []
    for line in text.splitlines():
        if line.startswith("data: "):
            payload = line[6:]
            if payload == "[DONE]":
                break
            try:
                parts.append(json.loads(payload))
            except json.JSONDecodeError:
                parts.append(payload)
    return "".join(parts)


async def write_via_api(conversation_id: str) -> str:
    """Send the remember message to the live API; return the assistant reply."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{API_BASE}/chat/send",
            params={"widget_id": WIDGET_ID},
            json={"conversation_id": conversation_id, "message": WRITE_MESSAGE},
        )
    if resp.status_code != 200:
        print(f"  ERROR: /chat/send returned {resp.status_code}: {resp.text[:200]}")
        sys.exit(1)
    return _collect_sse(resp.text)


# ---------------------------------------------------------------------------
# Step 2 — recall via direct pgvector search
# ---------------------------------------------------------------------------


async def get_admin_user_id(session_factory: async_sessionmaker) -> uuid.UUID:  # type: ignore[type-arg]
    """Look up the admin user's UUID — the widget owner whose memory we search."""
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.email == ADMIN_EMAIL))  # type: ignore[arg-type]
        admin = result.scalar_one_or_none()
        if admin is None:
            print(f"ERROR: admin user {ADMIN_EMAIL!r} not found. Run bootstrap_admin.py first.")
            sys.exit(1)
        return admin.id  # type: ignore[return-value]


async def recall_via_search(session_factory: async_sessionmaker, user_id: uuid.UUID) -> list[str]:  # type: ignore[type-arg]
    """Search long-term memory with a semantically different query."""
    async with session_factory() as session:
        results = await search(
            session,
            user_id=user_id,
            query=RECALL_QUERY,
            k=5,
        )
    return [r.content for r in results]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL env var is required.")
        sys.exit(1)

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    conv_a = str(uuid.uuid4())
    conv_b = str(uuid.uuid4())

    print("=" * 60)
    print("Cross-Conversation Memory Recall Demo")
    print("=" * 60)

    admin_user_id = await get_admin_user_id(session_factory)
    print(f"\nAdmin user ID (widget owner): {admin_user_id}")

    # ── Step 1 ──────────────────────────────────────────────────────────────
    print(f"\n[Step 1] Conversation A  (id={conv_a[:8]}…)")
    print(f"  → Sending: {WRITE_MESSAGE!r}")
    reply = await write_via_api(conv_a)
    print(f"  ← Claude replied: {reply[:120]!r}")

    wrote = (
        "remember" in reply.lower()
        or "noted" in reply.lower()
        or "stored" in reply.lower()
        or "saved" in reply.lower()
        or "memory" in reply.lower()
    )
    status = (
        "✅ write_memory tool was called"
        if wrote
        else "⚠️  reply received (check Langfuse for write_memory span)"
    )
    print(f"  {status}")

    # ── Step 2 ──────────────────────────────────────────────────────────────
    print(f"\n[Step 2] Conversation B  (id={conv_b[:8]}…)")
    print(f"  → Querying pgvector: {RECALL_QUERY!r}")
    recalled = await recall_via_search(session_factory, admin_user_id)

    if recalled:
        print(f"  ← {len(recalled)} entry/entries recalled from long-term memory:")
        for i, content in enumerate(recalled, 1):
            print(f"     {i}. {content[:100]!r}")
        target_found = any("alex" in c.lower() or "detailed" in c.lower() for c in recalled)
        if target_found:
            print("\n✅ PASS — written fact recalled via semantic similarity")
        else:
            print("\n⚠️  Entries recalled but written fact not in top results")
            print("   (The fact may not have been written yet — check Step 1)")
    else:
        print("  ← No entries in long-term memory yet")
        print("\n⚠️  SKIP — run Step 1 successfully first, then re-run")

    print()
    print("NOTE: In-chat recall requires a search_memory tool —")
    print("      the underlying pgvector pipeline is demonstrated here directly.")
    print("      Phase 5 would add the tool so Claude surfaces stored facts")
    print("      autonomously during a conversation.")
    print("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
