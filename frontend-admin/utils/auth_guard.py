"""Sidebar auth guard shared by all Streamlit pages."""

from __future__ import annotations

import streamlit as st


def require_auth() -> None:
    """Stop the page if the user is not logged in.

    When authenticated, renders the logged-in email and a Logout button in
    the sidebar.  Clears all session state on logout.
    """
    if "token" not in st.session_state:
        st.warning("Please log in from the Home page.")
        st.stop()

    email: str = st.session_state.get("email", "")
    st.sidebar.write(f"Logged in as: {email}")
    if st.sidebar.button("Logout"):
        for key in ("token", "email", "conversation_id", "messages"):
            st.session_state.pop(key, None)
        st.rerun()
