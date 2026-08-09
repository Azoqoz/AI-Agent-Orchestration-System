from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    task_id: str
    user_request: str
    planner_mode: str
    provider: str | None
    model: str | None
    plan: dict[str, Any]
    current_step_id: str | None
    tool_results: dict[str, Any]
    entity_context: dict[str, dict[str, str]]
    approval_status: str | None
    approval_reason: str | None
    recommended_action: str | None
    final_response: str | None
    generated_report_path: str | None
    customer_response: str | None
    status: str
    errors: list[str]
    created_at: str
    updated_at: str
    api_key: str | None
    display_error: str | None
    requested_planner: str
    executed_planner: str
    fallback_used: bool
    fallback_reason: str | None
    planning_notice: str | None
    planning_errors: list[str]
    unsupported_actions: list[str]
    failure_kind: str | None
