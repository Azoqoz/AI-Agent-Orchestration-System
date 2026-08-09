from __future__ import annotations

import logging

import streamlit as st

from src.agent.orchestrator import Orchestrator
from src.config import APP_MODE, APP_MODE_WARNING
from src.ui.history_view import render as render_history
from src.ui.layout import render_about
from src.ui.styles import CSS
from src.ui.workspace import render as render_workspace

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
st.set_page_config(page_title="AI Agent Orchestration System", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource
def get_orchestrator(app_mode: str) -> Orchestrator:
    return Orchestrator(app_mode=app_mode)


orchestrator = get_orchestrator(APP_MODE)
with st.sidebar:
    st.markdown("## ◈ Agent OS")
    page = st.radio("Navigate", ["Agent Workspace", "Task History", "Architecture / About"], label_visibility="collapsed")
    st.divider()
    st.caption(f"V1 · {APP_MODE.title()} mode · Fictional data")
    if APP_MODE_WARNING:
        st.warning(APP_MODE_WARNING)

if page == "Agent Workspace":
    render_workspace(orchestrator, APP_MODE)
elif page == "Task History":
    render_history(orchestrator.repo)
else:
    render_about(APP_MODE)
