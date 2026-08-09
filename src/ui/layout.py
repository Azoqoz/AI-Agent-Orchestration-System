from __future__ import annotations

import streamlit as st

from src.config import APP_MODE, normalize_app_mode


def render_about(app_mode: str = APP_MODE) -> None:
    app_mode = normalize_app_mode(app_mode)
    st.markdown("<div class='hero'><h1>Architecture</h1><p>A bounded, single-agent workflow with deterministic controls.</p></div>", unsafe_allow_html=True)
    st.graphviz_chart('''digraph { rankdir=LR; bgcolor="transparent"; node [shape=box style="rounded,filled" fillcolor="#151e32" color="#536b9d" fontcolor="#e6eaf2"]; edge [color="#7188b8"]; Planner -> Validator -> LangGraph -> Registry -> Approval -> Reports -> SQLite; }''', width="stretch")
    st.subheader("Planning modes")
    if app_mode == "demo":
        st.markdown("**Deterministic Planner** extracts explicit intents and IDs, orders dependencies, and runs the complete public demo without provider credentials.")
    else:
        st.markdown("**Deterministic Planner** extracts explicit intents and IDs, orders dependencies, and works completely offline.\n\n**LLM Planner** optionally asks OpenAI, Anthropic, Gemini, or Ollama for the same structured schema. Every LLM plan still passes the same validator; models never execute tools directly.")
    st.subheader("Safety boundary")
    st.info("All data is fictional. The system drafts recommendations and reports only—it does not transfer money, send email, or connect to a real CRM.")
