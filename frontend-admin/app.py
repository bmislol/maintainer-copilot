"""Maintainer's Copilot — Admin App.

This is the login page (the default Streamlit page).
Once authenticated, use the sidebar to navigate to Chat, Memory, or Widget Config.
"""

from __future__ import annotations

import streamlit as st

from utils.api_client import login

st.set_page_config(page_title="Maintainer's Copilot", page_icon="🤖", layout="centered")

# Already logged in — show sidebar and a "go to chat" prompt.
if "token" in st.session_state:
    email: str = st.session_state.get("email", "")
    st.sidebar.write(f"Logged in as: {email}")
    if st.sidebar.button("Logout"):
        for key in ("token", "email", "conversation_id", "messages"):
            st.session_state.pop(key, None)
        st.rerun()

    st.success(f"Logged in as **{email}**. Use the sidebar to navigate.")
    st.stop()

# Login form.
st.title("Maintainer's Copilot")
st.subheader("Login")

with st.form("login_form"):
    email_input = st.text_input("Email")
    password_input = st.text_input("Password", type="password")
    submitted = st.form_submit_button("Login")

if submitted:
    if not email_input or not password_input:
        st.error("Email and password are required.")
    else:
        try:
            token = login(email_input, password_input)
            st.session_state.token = token
            st.session_state.email = email_input
            st.rerun()
        except Exception as exc:
            st.error(f"Login failed: {exc}")
