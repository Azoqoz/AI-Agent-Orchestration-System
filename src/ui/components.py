from __future__ import annotations

from html import escape
import json
from typing import Any

import streamlit as st


STATUS_LABELS = {
    "completed": "Completed",
    "rejected": "Rejected",
    "failed": "Failed",
    "waiting_for_approval": "Waiting for approval",
    "pending": "Pending",
    "ready": "Ready",
    "running": "Running",
    "approved": "Approved",
    "skipped": "Skipped",
}


def result_for(state: dict[str, Any], name: str) -> dict[str, Any]:
    return state.get("tool_results", {}).get(name, {})


def planner_label(state: dict[str, Any]) -> str | None:
    if state.get("fallback_used"):
        return "LLM → Deterministic fallback"
    value = state.get("executed_planner") or state.get("planner_mode")
    if value == "llm": return "LLM"
    return str(value).replace("_", " ").title() if value else None


def status_badge(status: str | None) -> str:
    value = status or "pending"
    label = STATUS_LABELS.get(value, value.replace("_", " ").title())
    return f"<span class='status-badge status-{escape(value)}'>{escape(label)}</span>"


def _money(value: Any) -> str | None:
    if value in (None, ""): return None
    try: return f"${float(value):,.2f}"
    except (TypeError, ValueError): return f"${value}"


def _hours(value: Any) -> str | None:
    if value in (None, ""): return None
    try:
        number = abs(float(value))
        return f"{number:g} hours"
    except (TypeError, ValueError):
        return f"{value} hours"


def _open_case_summary(customer: dict[str, Any]) -> str | None:
    cases = customer.get("open_cases") or []
    if not cases: return None
    return "; ".join(
        f"{case.get('case_id')} · {case.get('case_type')}/{case.get('status')} · {case.get('description')}"
        for case in cases
    )


def summary_fields(state: dict[str, Any]) -> list[tuple[str, str]]:
    customer = result_for(state, "customer_lookup")
    case = result_for(state, "case_lookup")
    refund = result_for(state, "refund_calculator")
    fields = [
        ("Task ID", state.get("task_id")),
        ("Status", STATUS_LABELS.get(state.get("status"), str(state.get("status", "")).replace("_", " ").title())),
        ("Planner mode", planner_label(state)),
        ("Customer ID", customer.get("customer_id")),
        ("Case ID", case.get("case_id")),
        ("Recommended refund", _money(refund.get("final_recommended_refund"))),
        ("Approval status", STATUS_LABELS.get(state.get("approval_status"), state.get("approval_status"))),
    ]
    return [(label, str(value)) for label, value in fields if value not in (None, "")]


def show_summary(state: dict[str, Any]) -> None:
    fields = summary_fields(state)
    if not fields: return
    cards = "".join(
        f"<div class='summary-card'><span>{escape(label)}</span><strong>{escape(value)}</strong></div>"
        for label, value in fields
    )
    st.markdown(f"<div class='summary-grid'>{cards}</div>", unsafe_allow_html=True)


def show_plan(state: dict[str, Any]) -> None:
    plan = state.get("plan") or {}
    if not plan:
        st.info("No execution plan is available for this task.")
        return
    if plan.get("summary"): st.caption(plan["summary"])
    for step in plan.get("steps", []):
        name = step.get("description") or step.get("tool_name", "Workflow step")
        tool = step.get("tool_name", "")
        reason = step.get("reason") or ""
        st.markdown(
            "<div class='step-card'>"
            f"<div><strong>{escape(name)}</strong><span class='step-tool'>{escape(tool)}</span>"
            f"<p>{escape(reason)}</p></div>{status_badge(step.get('status'))}</div>",
            unsafe_allow_html=True,
        )
        with st.expander(f"Step details · {step.get('step_id', tool)}"):
            st.json({
                "inputs": step.get("inputs", {}),
                "depends_on": step.get("depends_on", []),
                "requires_approval": step.get("requires_approval", False),
            })


def _result_summary(output: dict[str, Any]) -> str:
    for key in ("eligibility", "priority", "final_recommended_refund", "explanation", "count", "customer_id", "case_id"):
        if key in output:
            value = output[key]
            return f"{key.replace('_', ' ').title()}: {value}"
    return "Tool completed successfully"


def show_trace(state: dict[str, Any]) -> None:
    results = state.get("tool_results") or {}
    if not results:
        st.info("No tool executions have been recorded yet.")
        return
    step_status = {s.get("tool_name"): s.get("status") for s in (state.get("plan") or {}).get("steps", [])}
    for name, output in results.items():
        output = output if isinstance(output, dict) else {"result": output}
        status = step_status.get(name, "completed")
        latency = output.get("_latency_ms")
        duration = f"{latency} ms" if latency is not None else "Duration not recorded"
        st.markdown(
            "<div class='trace-row'>"
            f"<div><strong>{escape(name.replace('_', ' ').title())}</strong>"
            f"<p>{escape(_result_summary(output))}</p></div>"
            f"<div class='trace-meta'>{status_badge(status)}<span>{escape(duration)}</span></div></div>",
            unsafe_allow_html=True,
        )
        with st.expander(f"Raw output · {name}"):
            st.json(output)


def show_validation_details(state: dict[str, Any]) -> None:
    with st.expander("Plan and validation details"):
        plan = state.get("plan") or {}
        st.json({"task_type": plan.get("task_type"), "planner_mode": plan.get("planner_mode"),
                 "fallback_reason": state.get("fallback_reason"), "planning_errors": state.get("planning_errors", []),
                 "errors": state.get("errors", [])})
    with st.expander("Complete task state"):
        safe_state = {k: v for k, v in state.items() if k != "api_key"}
        st.json(safe_state)


def approval_summary(state: dict[str, Any]) -> None:
    customer = result_for(state, "customer_lookup")
    case = result_for(state, "case_lookup")
    policy = result_for(state, "policy_checker")
    refund = result_for(state, "refund_calculator")
    priority = result_for(state, "priority_classifier")
    sla = result_for(state, "sla_checker")
    values = [
        ("Customer", customer.get("customer_id")),
        ("Case", case.get("case_id")),
        ("Eligibility", policy.get("eligibility")),
        ("Recommended refund", _money(refund.get("final_recommended_refund"))),
        ("Priority", priority.get("priority")),
        ("SLA", "Breached" if sla.get("breached") is True else "Within SLA" if sla.get("breached") is False else None),
    ]
    facts = "".join(
        f"<div><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>"
        for label, value in values if value not in (None, "")
    )
    reason = policy.get("reason") or state.get("recommended_action") or "Review the available evidence before deciding."
    st.markdown(
        "<div class='approval-card'><div class='card-heading'>"
        f"<div><span class='eyebrow'>HUMAN REVIEW</span><h3>Approval required</h3></div>{status_badge('waiting_for_approval')}"
        f"</div><div class='approval-facts'>{facts}</div><div class='reason-box'><span>Reason</span><p>{escape(reason)}</p></div></div>",
        unsafe_allow_html=True,
    )


def final_decision_fields(state: dict[str, Any]) -> list[tuple[str, str]]:
    """Return only the task results that the workflow actually produced."""
    policy = result_for(state, "policy_checker")
    priority = result_for(state, "priority_classifier")
    sla = result_for(state, "sla_checker")
    refund = result_for(state, "refund_calculator")
    customer = result_for(state, "customer_lookup")
    case = result_for(state, "case_lookup")
    history = result_for(state, "task_history_search")
    history_task = (history.get("tasks") or [{}])[0] if history else {}
    approval = state.get("approval_status")
    planned_tools = {step.get("tool_name") for step in (state.get("plan") or {}).get("steps", [])}
    response_only = "generate_customer_response" in planned_tools and not refund
    generic_case_lookup = planned_tools == {"case_lookup"}

    sla_status = None
    if sla.get("breached") is True:
        sla_status = "Breached"
    elif sla.get("breached") is False:
        sla_status = "Within SLA"

    remaining_label = None
    remaining_value = None
    if sla.get("remaining_hours") not in (None, ""):
        try:
            remaining_label = "Overdue hours" if float(sla["remaining_hours"]) < 0 else "Remaining hours"
        except (TypeError, ValueError):
            remaining_label = "Remaining hours"
        remaining_value = _hours(sla["remaining_hours"])

    values = [
        ("Outcome", STATUS_LABELS.get(state.get("status"), str(state.get("status", "")).title())),
        ("Case ID", case.get("case_id") if response_only or generic_case_lookup else None),
        ("Customer ID", customer.get("customer_id") or case.get("customer_id") if generic_case_lookup else customer.get("customer_id")),
        ("Case type", str(case.get("case_type", "")).title() or None if generic_case_lookup else None),
        ("Case status", str(case.get("status", "")).title() or None if generic_case_lookup else None),
        ("Issue", case.get("description") if generic_case_lookup else None),
        ("Created", case.get("created_at") if generic_case_lookup else None),
        ("Order ID", case.get("order_id") if generic_case_lookup else None),
        ("Purchase amount", _money(case.get("amount_paid")) if generic_case_lookup else None),
        ("Purchase date", case.get("purchase_date") if generic_case_lookup else None),
        ("Purchase age", f"{case['purchase_age_days']} days" if generic_case_lookup and case.get("purchase_age_days") not in (None, "") else None),
        ("Usage", f"{float(case['usage_percent']):g}%" if generic_case_lookup and case.get("usage_percent") not in (None, "") else None),
        ("Account status", str(customer.get("account_status", "")).title() or None),
        ("Open cases", customer.get("open_case_count")),
        ("Open case summary", _open_case_summary(customer)),
        ("Eligibility", policy.get("eligibility")),
        ("Human review required", "Yes" if policy.get("human_review_required") is True else "No" if policy.get("human_review_required") is False else None),
        ("Policy reason", policy.get("reason")),
        ("Priority", priority.get("priority") or sla.get("priority")),
        ("SLA status", sla_status),
        ("SLA breached", "Yes" if sla.get("breached") is True else "No" if sla.get("breached") is False else None),
        (remaining_label, remaining_value),
        ("Recommended refund", _money(refund.get("final_recommended_refund"))),
        ("Approval decision", STATUS_LABELS.get(approval, approval)),
        ("Report generated", "Yes" if state.get("generated_report_path") else "No" if "generate_report" in planned_tools else None),
        ("Customer response ready", "Yes" if state.get("customer_response") else "No" if "generate_customer_response" in planned_tools else None),
        ("Retrieved task ID", history_task.get("id")),
        ("Retrieved case ID", history_task.get("case_id")),
        ("Retrieved customer ID", history_task.get("customer_id")),
        ("Retrieved refund", _money(history_task.get("refund_amount"))),
        ("Retrieved approval", STATUS_LABELS.get(history_task.get("approval_status"), history_task.get("approval_status"))),
        ("Completed", history_task.get("completed_at")),
    ]
    return [(str(label), str(value)) for label, value in values if label and value not in (None, "")]


def show_final_decision(state: dict[str, Any]) -> None:
    values = final_decision_fields(state)
    facts = "".join(
        f"<div><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>"
        for label, value in values
    )
    st.markdown(f"<div class='decision-card'><h3>Final decision</h3><div class='decision-facts'>{facts}</div></div>", unsafe_allow_html=True)
    if state.get("final_response"):
        st.markdown("#### Final message")
        st.markdown(state["final_response"])


def json_value(value: Any) -> Any:
    """Decode persisted JSON values for history views without failing on old rows."""
    if value in (None, ""): return None
    try: return json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError): return value
