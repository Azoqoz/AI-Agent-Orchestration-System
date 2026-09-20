from __future__ import annotations

from dataclasses import dataclass
import re


DEMO_MAX_REQUEST_LENGTH = 500
DEMO_MAX_TASKS_PER_SESSION = 25
DEMO_MAX_HISTORY_LIMIT = 20
DEMO_RETENTION_HOURS = 24

_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,64}$")


@dataclass(frozen=True)
class GuidedDemoTaskSpec:
    id: str
    title: str
    user_request: str
    expected_tools: tuple[str, ...]
    demonstrates_approval: bool = False
    expected_status: str = "completed"


GUIDED_DEMO_TASKS = (
    GuidedDemoTaskSpec(
        id="refund-review",
        title="Refund review with approval",
        user_request="Review CASE-220, check eligibility, calculate the refund, and prepare a customer response.",
        expected_tools=(
            "case_lookup",
            "customer_lookup",
            "policy_checker",
            "refund_calculator",
            "generate_report",
            "generate_customer_response",
        ),
        demonstrates_approval=True,
        expected_status="waiting_for_approval",
    ),
    GuidedDemoTaskSpec(
        id="priority-and-sla",
        title="Priority and SLA",
        user_request="Determine the priority and SLA status of CASE-225.",
        expected_tools=("case_lookup", "priority_classifier", "sla_checker"),
    ),
    GuidedDemoTaskSpec(
        id="customer-overview",
        title="Customer overview",
        user_request="Check customer CUST-104 and summarize all open cases.",
        expected_tools=("customer_lookup",),
    ),
    GuidedDemoTaskSpec(
        id="task-memory",
        title="Task memory",
        user_request="Show the most recent approved refund case.",
        expected_tools=("task_history_search",),
    ),
    GuidedDemoTaskSpec(
        id="guardrail-example",
        title="Guardrail example",
        user_request="Execute a refund and send the customer a confirmation message.",
        expected_tools=(),
        expected_status="failed",
    ),
)


def validate_demo_session_id(value: str | None) -> str:
    session_id = (value or "").strip()
    if not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError("Demo Mode requires a valid opaque session identifier")
    return session_id
