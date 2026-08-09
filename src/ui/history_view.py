from __future__ import annotations

from datetime import datetime
from html import escape

import streamlit as st

from src.memory.repositories import Repository
from src.ui.components import json_value, planner_label, status_badge


def _date(value: str | None) -> str:
    if not value: return ""
    try: return datetime.fromisoformat(value).strftime("%b %d, %Y · %H:%M")
    except ValueError: return value


def _summary(detail: dict) -> None:
    state = detail.get("state") or {}
    values = [
        ("Task ID", detail.get("id")),
        ("Status", str(detail.get("status", "")).replace("_", " ").title()),
        ("Planner", planner_label(state) or str(detail.get("planner_mode", "")).title()),
        ("Created", _date(detail.get("created_at"))),
        ("Tools used", len([s for s in detail.get("steps", []) if s.get("status") == "completed"])),
    ]
    cards = "".join(f"<div class='summary-card'><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>" for label, value in values if value not in (None, ""))
    st.markdown(f"<div class='summary-grid'>{cards}</div>", unsafe_allow_html=True)
    st.markdown("#### User request")
    st.markdown(f"<div class='request-card'>{escape(detail.get('user_request') or '')}</div>", unsafe_allow_html=True)


def _workflow_steps(detail: dict) -> None:
    steps = detail.get("steps") or []
    if not steps:
        st.info("No workflow steps were recorded.")
        return
    for step in steps:
        description = step.get("description") or step.get("reason") or "Workflow step"
        st.markdown(
            "<div class='step-card'>"
            f"<div><strong>{escape(description)}</strong><span class='step-tool'>{escape(step.get('tool_name') or '')}</span>"
            f"<p>{escape(step.get('reason') or '')}</p></div>{status_badge(step.get('status'))}</div>",
            unsafe_allow_html=True,
        )
        with st.expander(f"Step details · {step.get('step_id')}"):
            st.caption(f"Latency: {step.get('latency_ms')} ms" if step.get("latency_ms") is not None else "Latency not recorded")
            st.json({"input": json_value(step.get("tool_input_json")), "output": json_value(step.get("tool_output_json")), "error": step.get("error_message")})


def _approval(detail: dict) -> None:
    approvals = detail.get("approvals") or []
    if not approvals:
        st.info("No approval decision was required or recorded.")
        return
    for item in approvals:
        decision = item.get("decision") or "pending"
        st.markdown(
            "<div class='approval-history'><div>"
            f"<strong>Reviewer decision</strong><p>{escape(item.get('reason') or 'No reviewer note provided.')}</p>"
            f"<span>{escape(_date(item.get('decided_at')))}</span></div>{status_badge(decision)}</div>",
            unsafe_allow_html=True,
        )


def _technical(detail: dict) -> None:
    with st.expander("Task metadata"):
        state = detail.get("state") or {}
        st.json({"provider": detail.get("provider"), "requested_planner": state.get("requested_planner"),
                 "executed_planner": state.get("executed_planner"), "fallback_used": state.get("fallback_used"),
                 "fallback_reason": state.get("fallback_reason"), "updated_at": detail.get("updated_at"),
                 "completed_at": detail.get("completed_at"), "report_path": detail.get("report_path")})
    with st.expander("Audit events"): st.json(detail.get("events") or [])
    with st.expander("Persisted state"): st.json(detail.get("state") or {})


def render(repo: Repository) -> None:
    st.markdown("<div class='hero'><h1>Task History</h1><p>Search and review persistent workflow audit records.</p></div>", unsafe_allow_html=True)
    keyword = st.text_input("Search tasks", placeholder="Request text, case ID, or customer ID")
    rows = repo.search_tasks(keyword=keyword or None, limit=50)
    if not rows:
        st.info("No matching tasks yet.")
        return
    table_rows = [{
        "Task ID": row["id"], "User request": row["user_request"],
        "Status": str(row["status"]).replace("_", " ").title(),
        "Planner mode": ("LLM → Deterministic fallback" if row.get("fallback_used") else
                         "LLM" if row.get("executed_planner") == "llm" else
                         str(row.get("executed_planner") or row["planner_mode"]).replace("_", " ").title()),
        "Created date": _date(row.get("created_at")), "Tools used": row.get("tools_used", 0),
    } for row in rows]
    st.dataframe(table_rows, width="stretch", hide_index=True, column_config={
        "Task ID": st.column_config.TextColumn(width="small"), "User request": st.column_config.TextColumn(width="large"),
        "Status": st.column_config.TextColumn(width="medium"), "Planner mode": st.column_config.TextColumn(width="small"),
        "Created date": st.column_config.TextColumn(width="medium"), "Tools used": st.column_config.NumberColumn(width="small"),
    })
    selected = st.selectbox("Open task", [row["id"] for row in rows])
    detail = repo.task_detail(selected)
    if not detail: return
    st.markdown(f"<div class='detail-heading'><div><span class='eyebrow'>TASK DETAIL</span><h2>{escape(selected)}</h2></div>{status_badge(detail.get('status'))}</div>", unsafe_allow_html=True)
    summary, workflow, approval, response, technical = st.tabs(["Summary", "Workflow Steps", "Approval Decision", "Final Response", "Technical Details"])
    with summary: _summary(detail)
    with workflow: _workflow_steps(detail)
    with approval: _approval(detail)
    with response:
        if detail.get("final_response"):
            with st.container(border=True): st.markdown(detail["final_response"])
        else: st.info("No final response was recorded.")
        if detail.get("customer_response"):
            with st.expander("Customer-response draft"): st.markdown(detail["customer_response"])
    with technical: _technical(detail)
