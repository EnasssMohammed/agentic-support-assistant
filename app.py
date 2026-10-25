"""Velo platform: Home, Velo Agent (customer view) and Team Inbox.

Run:  streamlit run app.py
Set VELO_DEBUG=1 to show internal error details (never enable in production).
"""

import streamlit as st

from ui import theme
from ui.pages import (
    AGENT,
    HOME,
    INBOX,
    init_state,
    render_customer,
    render_home,
    render_inbox,
)
from ui.tickets import load_tickets

st.set_page_config(
    page_title="Velo",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_state()
theme.inject()

SOON = (
    "Knowledge Management Studio",
    "Evaluation Lab",
    "Analytics & Reports",
    "Workflows",
    "Integrations",
    "Settings",
)

open_tickets = sum(1 for t in load_tickets() if t["status"] != "closed")
LABELS = {
    HOME: "Home",
    AGENT: "Velo Agent",
    INBOX: f"Team Inbox ({open_tickets})" if open_tickets else "Team Inbox",
}

with st.sidebar:
    st.markdown(
        '<div class="brand"><div class="brand-mark">V</div><div>'
        '<div class="brand-name">Velo</div><div class="brand-sub">AI support platform</div>'
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown('<div class="nav-label">Workspace</div>', unsafe_allow_html=True)
    st.radio(
        "Navigation",
        (HOME, AGENT, INBOX),
        key="page",
        label_visibility="collapsed",
        format_func=LABELS.get,
    )
    st.markdown('<div class="nav-label">Coming soon</div>', unsafe_allow_html=True)
    st.markdown(
        "".join(f'<div class="nav-soon">{theme.esc(name)}<i>Soon</i></div>' for name in SOON),
        unsafe_allow_html=True,
    )

ROUTES = {HOME: render_home, AGENT: render_customer, INBOX: render_inbox}
ROUTES[st.session_state.page]()
