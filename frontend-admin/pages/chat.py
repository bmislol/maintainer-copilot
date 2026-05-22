"""Chat page — Phase 4.4."""

from __future__ import annotations

import uuid

import streamlit as st

from utils.api_client import send_message_stream
from utils.auth_guard import require_auth

st.set_page_config(page_title="Chat — Maintainer's Copilot", page_icon="💬")
require_auth()

st.title("Chat")

# Initialise session state.
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# New Conversation button sits top-right.
_, col_btn = st.columns([5, 1])
with col_btn:
    if st.button("New", help="Start a new conversation"):
        st.session_state.conversation_id = None
        st.session_state.messages = []
        st.rerun()

# Render chat history.
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Conversation-id footer — visible even before the first message.
if st.session_state.conversation_id:
    st.caption(f"Conversation: {st.session_state.conversation_id}")

# Chat input.
if prompt := st.chat_input("Ask about an issue…"):
    # Assign a conversation_id client-side on the first turn so the server
    # persists history under a stable key and we can display it immediately.
    if not st.session_state.conversation_id:
        st.session_state.conversation_id = str(uuid.uuid4())

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        response: str = st.write_stream(  # type: ignore[assignment]
            send_message_stream(
                st.session_state.token,
                prompt,
                st.session_state.conversation_id,
            )
        )

    st.session_state.messages.append({"role": "assistant", "content": response})
    st.caption(f"Conversation: {st.session_state.conversation_id}")
