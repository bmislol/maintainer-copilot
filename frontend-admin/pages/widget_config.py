"""Widget Config page — placeholder (Phase 4.6)."""

from __future__ import annotations

import streamlit as st

from utils.auth_guard import require_auth

st.set_page_config(page_title="Widget Config — Maintainer's Copilot", page_icon="⚙️")
require_auth()

st.title("Widget Configuration")
st.info("Widget configuration coming in Phase 4.6.")
