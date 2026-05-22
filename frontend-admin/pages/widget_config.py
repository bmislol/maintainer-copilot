"""Widget Configuration — create or edit embed widgets (Phase 4.6)."""

from __future__ import annotations

import os

import streamlit as st

from utils.api_client import create_widget, get_my_widgets, update_widget
from utils.auth_guard import require_auth

st.set_page_config(page_title="Widget Config — Maintainer's Copilot", page_icon="⚙️")
require_auth()

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.title("Widget Configuration")

token: str = st.session_state["token"]

# ── Load existing widgets ────────────────────────────────────────────────────
try:
    my_widgets: list[dict] = get_my_widgets(token)  # type: ignore[type-arg]
except Exception as exc:
    st.error(f"Could not load widgets: {exc}")
    my_widgets = []

# ── Select existing or create new ───────────────────────────────────────────
widget_options = ["— Create new widget —"] + [
    f"{w['name']} ({str(w['id'])[:8]}…)" for w in my_widgets
]
selection = st.selectbox("Select widget", widget_options)

selected_widget: dict | None = None  # type: ignore[type-arg]
if selection != "— Create new widget —":
    idx = widget_options.index(selection) - 1
    selected_widget = my_widgets[idx]

# ── Form ─────────────────────────────────────────────────────────────────────
with st.form("widget_form"):
    name = st.text_input(
        "Widget name",
        value=selected_widget["name"] if selected_widget else "My Widget",
        max_chars=128,
    )
    theme = st.selectbox(
        "Theme",
        ["dark", "light"],
        index=0 if (not selected_widget or selected_widget.get("theme") == "dark") else 1,
    )
    greeting = st.text_input(
        "Greeting message",
        value=selected_widget["greeting"] if selected_widget else "Hello! How can I help?",
        max_chars=512,
    )
    tool_options = ["retrieve_docs", "classify_issue", "extract_entities", "summarize_thread"]
    default_tools: list[str] = (
        selected_widget["enabled_tools"] if selected_widget else ["retrieve_docs"]
    )
    enabled_tools = st.multiselect(
        "Enabled tools",
        options=tool_options,
        default=[t for t in default_tools if t in tool_options],
    )
    origins_raw = st.text_area(
        "Allowed origins (one per line)",
        value="\n".join(selected_widget["allowed_origins"]) if selected_widget else "",
        height=120,
        help="e.g. http://localhost:8080  — browsers block embedding from other origins",
    )
    submitted = st.form_submit_button(
        "Update widget" if selected_widget else "Create widget"
    )

if submitted:
    allowed_origins = [o.strip() for o in origins_raw.splitlines() if o.strip()]
    try:
        if selected_widget:
            result: dict = update_widget(  # type: ignore[type-arg]
                token,
                str(selected_widget["id"]),
                patch={
                    "name": name,
                    "theme": theme,
                    "greeting": greeting,
                    "enabled_tools": enabled_tools,
                    "allowed_origins": allowed_origins,
                },
            )
            st.success(f"Widget updated: {result['name']}")
        else:
            result = create_widget(
                token,
                name=name,
                theme=theme,
                greeting=greeting,
                enabled_tools=enabled_tools,
                allowed_origins=allowed_origins,
            )
            st.success(f"Widget created: {result['name']}")
    except Exception as exc:
        st.error(f"Error: {exc}")
        st.stop()

    # ── Embed snippet ─────────────────────────────────────────────────────────
    widget_id = str(result["id"])
    st.subheader("Embed snippet")
    snippet = (
        f'<script\n'
        f'  src="{API_URL}/loader.js"\n'
        f'  data-widget-id="{widget_id}"\n'
        f'  data-api-base="{API_URL}">\n'
        f'</script>'
    )
    st.code(snippet, language="html")
    st.caption(
        f"Paste this into any HTML page whose origin is in the allowed list above. "
        f"Widget ID: `{widget_id}`"
    )
