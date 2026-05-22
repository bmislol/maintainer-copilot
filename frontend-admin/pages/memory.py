"""Memory Inspector page — Phase 4.4."""

from __future__ import annotations

import streamlit as st

from utils.api_client import get_memory_entries
from utils.auth_guard import require_auth

st.set_page_config(page_title="Memory — Maintainer's Copilot", page_icon="🧠")
require_auth()

st.title("Memory Inspector")
st.caption("Your long-term memory entries, newest first (read-only).")

if st.button("Refresh"):
    st.rerun()

try:
    entries: list[dict] = get_memory_entries(st.session_state.token)  # type: ignore[type-arg]
except Exception as exc:
    st.error(f"Failed to load memory entries: {exc}")
    st.stop()

if not entries:
    st.info("No memory entries yet. Ask the chatbot to remember something using the write_memory tool.")
else:
    for entry in entries:
        preview = entry["content"][:80] + ("…" if len(entry["content"]) > 80 else "")
        with st.expander(f"[{entry['memory_type']}]  {preview}"):
            st.write(f"**Content:** {entry['content']}")
            st.write(f"**Type:** {entry['memory_type']}")
            st.write(f"**Created:** {entry['created_at']}")
            st.caption(f"ID: {entry['id']}")
