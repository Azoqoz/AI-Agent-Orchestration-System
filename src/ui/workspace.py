from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from src.agent.orchestrator import Orchestrator
from src.config import APP_MODE, normalize_app_mode
from src.ui.components import (
    approval_summary,
    show_final_decision,
    show_plan,
    show_summary,
    show_trace,
    show_validation_details,
)

EXAMPLES = [
    "Review CASE-220, check eligibility, calculate the refund, and prepare a customer response.",
    "Check customer CUST-104 and summarize all open cases.",
    "Determine the priority and SLA status of CASE-225.",
    "Show the most recent approved refund case.",
]
LLM_PROVIDERS = ("OpenAI", "Anthropic", "Gemini", "Ollama")
DEFAULT_OLLAMA_MODEL = "llama3.2"

V1_CAPABILITIES = (
    "Review a case",
    "Check refund eligibility",
    "Calculate a refund recommendation",
    "Determine priority and SLA status",
    "Summarize a customer's open cases",
    "Search task history / find previous approved refund cases",
    "Generate an internal report",
    "Draft a customer response",
)

V1_LIMITATIONS = (
    "Sending emails or SMS",
    "Executing real refunds/payments",
    "Deleting or modifying customer or case records",
    "Arbitrary external system writes",
)

MODE_PRESENTATION = {
    "demo": {
        "badge": "DEMO MODE",
        "description": "Public demo using fictional customer data and deterministic agent planning.",
        "planner_options": ("Offline / Deterministic",),
        "show_planning_settings": False,
    },
    "local": {
        "badge": "LOCAL FULL MODE",
        "description": "Full local workspace with deterministic and optional LLM planning.",
        "planner_options": ("Offline / Deterministic", "LLM"),
        "show_planning_settings": True,
    },
}


def mode_presentation(app_mode: str) -> dict[str, Any]:
    return MODE_PRESENTATION[normalize_app_mode(app_mode)]


def provider_requires_api_key(provider: str) -> bool:
    return provider.lower() != "ollama"


def demo_data_guide(orchestrator: Orchestrator, app_mode: str) -> None:
    """Render a compact, user-facing catalog without exposing database details."""
    catalog = orchestrator.repo.demo_record_catalog()
    customer_ids = catalog["customer_ids"]
    case_ids = catalog["case_ids"]
    with st.expander("Demo Data Guide", expanded=False):
        st.caption("Fictional records available for safe experimentation.")
        counts = st.columns(2)
        counts[0].metric("Customers", len(customer_ids))
        counts[1].metric("Cases", len(case_ids))
        st.markdown(f"**Customer IDs:** `{'`, `'.join(customer_ids)}`")
        st.markdown(f"**Case IDs:** `{'`, `'.join(case_ids)}`")
        capability_col, limitation_col = st.columns(2)
        with capability_col:
            st.markdown("**You can ask the agent to:**")
            st.markdown("\n".join(f"- {capability}" for capability in V1_CAPABILITIES))
        with limitation_col:
            st.markdown("**Not supported in V1:**")
            st.markdown("\n".join(f"- {limitation}" for limitation in V1_LIMITATIONS))
        if app_mode == "local":
            st.caption("LLM planning is optional; all demo workflows also support deterministic planning.")


def _select_demo(example: str) -> None:
    """Populate the task widget before Streamlit instantiates it on the rerun."""
    st.session_state["task_input"] = example


def _clear_workspace() -> None:
    """Reset transient workspace state without touching persisted task records."""
    st.session_state["task_input"] = ""
    st.session_state.pop("active_state", None)


def _configured_secret(provider: str) -> str | None:
    key_name = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}.get(provider)
    if not key_name: return None
    try: return st.secrets.get(key_name) or None
    except Exception: return None


def _downloads(state: dict, key_prefix: str) -> None:
    report_path = state.get("generated_report_path")
    has_report = report_path and Path(report_path).exists()
    has_response = bool(state.get("customer_response"))
    if not has_report and not has_response: return
    st.markdown("#### Downloads")
    columns = st.columns(2)
    if has_report:
        path = Path(report_path)
        columns[0].download_button("Download internal report", path.read_bytes(), file_name=path.name, mime="text/markdown", key=f"{key_prefix}_report", width="stretch")
    if has_response:
        columns[1].download_button("Download customer response", state["customer_response"], file_name=f"{state['task_id']}_response.txt", mime="text/plain", key=f"{key_prefix}_response", width="stretch")


def _approval_gate(orchestrator: Orchestrator, state: dict) -> None:
    approval_summary(state)
    note = st.text_area("Reviewer note", key=f"reason_{state['task_id']}", height=72, placeholder="Optional context for the audit trail")
    approve, reject = st.columns(2)
    if approve.button("Approve", type="primary", width="stretch", key=f"approve_{state['task_id']}"):
        st.session_state.active_state = orchestrator.resume(state["task_id"], "approved", note)
        st.rerun()
    if reject.button("Reject", width="stretch", key=f"reject_{state['task_id']}"):
        st.session_state.active_state = orchestrator.resume(state["task_id"], "rejected", note)
        st.rerun()


def _customer_response(state: dict) -> None:
    response = state.get("customer_response")
    if not response:
        st.info("The customer response will appear here when the workflow produces one.")
        return
    st.markdown("<div class='response-heading'><span class='eyebrow'>CUSTOMER-FACING DRAFT</span><h3>Response ready for review</h3></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(response)
    with st.expander("Copy-ready text"):
        st.caption("Use the copy button in the text box.")
        st.code(response, language=None)
    st.download_button("Download response", response, file_name=f"{state['task_id']}_response.txt", mime="text/plain", key=f"customer_tab_{state['task_id']}")


def render(orchestrator: Orchestrator, app_mode: str = APP_MODE) -> None:
    app_mode = normalize_app_mode(app_mode)
    presentation = mode_presentation(app_mode)
    st.markdown(
        f"<div class='hero'><span class='badge'>{presentation['badge']}</span>"
        f"<h1>Customer Operations Agent</h1><p>{presentation['description']}</p></div>",
        unsafe_allow_html=True,
    )
    st.markdown("#### Demo workflows")
    cols = st.columns(2)
    for index, example in enumerate(EXAMPLES):
        cols[index % 2].button(
            example,
            key=f"example_{index}",
            width="stretch",
            on_click=_select_demo,
            args=(example,),
        )
    demo_data_guide(orchestrator, app_mode)
    mode_label = "Offline / Deterministic"
    provider = api_key = model = None
    if presentation["show_planning_settings"]:
        with st.expander("Planning settings"):
            mode_label = st.radio("Planning mode", presentation["planner_options"], horizontal=True)
            if mode_label == "LLM":
                provider = st.selectbox("Provider", LLM_PROVIDERS).lower()
                if not provider_requires_api_key(provider):
                    model = st.text_input("Ollama model", value=DEFAULT_OLLAMA_MODEL, help="A model installed in your local Ollama instance.") or DEFAULT_OLLAMA_MODEL
                    st.caption("Uses the local Ollama endpoint at http://localhost:11434 (or OLLAMA_URL). No API key is required.")
                else:
                    api_key = st.text_input("Session-only API key", type="password", help="Kept in this session and never persisted.") or _configured_secret(provider)
            st.caption("Deterministic mode runs the full workflow without a provider key.")
    else:
        st.caption("Use fictional demo IDs only. Do not enter real personal or business data.")
    if app_mode == "demo":
        st.caption("Use the fictional IDs shown in Demo Data Guide, or choose one of the example workflows above.")
    request = st.text_area("Task", key="task_input", height=104, placeholder="Review CASE-220, check eligibility, calculate the refund, and prepare a response.")
    run_col, clear_col = st.columns([3, 1])
    if run_col.button("Run agent", type="primary", width="stretch"):
        try:
            st.session_state.active_state = orchestrator.start(request, "llm" if mode_label == "LLM" else "deterministic", provider, api_key, model)
        except Exception as exc:
            st.error(f"Could not start the task: {exc}")
    clear_col.button("Clear", width="stretch", on_click=_clear_workspace)

    state = st.session_state.get("active_state")
    if not state: return
    st.divider()
    if state.get("errors"):
        st.error(state.get("display_error") or "The task could not be completed. See Execution Details for technical information.")
        if app_mode == "demo":
            st.info("The hosted demo supports Customer Operations workflows using the fictional customer and case IDs shown in the examples.")

    overview, workflow, execution, customer = st.tabs(["Overview", "Workflow", "Execution Details", "Customer Response"])
    with overview:
        if state.get("planning_notice"): st.info(state["planning_notice"])
        show_summary(state)
        if state.get("status") == "waiting_for_approval": _approval_gate(orchestrator, state)
        if state.get("status") in {"completed", "rejected", "failed"} or state.get("final_response"):
            show_final_decision(state)
        _downloads(state, f"overview_{state['task_id']}")
    with workflow:
        st.markdown("### Execution plan")
        show_plan(state)
    with execution:
        st.markdown("### Execution trace")
        show_trace(state)
        st.markdown("### Technical details")
        show_validation_details(state)
    with customer:
        _customer_response(state)
