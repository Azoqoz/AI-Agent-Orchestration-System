from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.orchestrator import Orchestrator
from src.memory.database import Database
from src.services import (
    ApprovalRecord,
    ApprovalService,
    AuditEventRecord,
    HistoryService,
    InvalidApproval,
    InvalidTaskRequest,
    PendingApproval,
    PlannerMode,
    ProviderName,
    ProviderService,
    StartTaskRequest,
    TaskDetail,
    TaskHistoryQuery,
    TaskNotFound,
    TaskService,
    TaskSummary,
    ToolExecutionResult,
    WorkflowStatus,
)


APPROVAL_TASK = "Review CASE-220, check eligibility, calculate the refund, and prepare a customer response."


def _services(orchestrator: Orchestrator) -> tuple[TaskService, ApprovalService, HistoryService]:
    tasks = TaskService(orchestrator)
    return tasks, ApprovalService(tasks), HistoryService(orchestrator.repo)


def _llm_case_plan() -> str:
    return json.dumps(
        {
            "task_type": "customer_operations",
            "planner_mode": "llm",
            "summary": "Review the requested case.",
            "steps": [
                {
                    "step_id": "step_1",
                    "tool_name": "case_lookup",
                    "description": "Review case",
                    "reason": "Load the referenced case facts.",
                    "inputs": {"case_id": "CASE-220"},
                    "depends_on": [],
                    "requires_approval": False,
                    "status": "pending",
                }
            ],
        }
    )


def test_task_service_starts_deterministic_task_and_returns_typed_detail(orchestrator: Orchestrator) -> None:
    tasks, _, _ = _services(orchestrator)

    detail = tasks.start_task(StartTaskRequest(user_request="Determine priority and SLA status of CASE-225."))

    assert isinstance(detail, TaskDetail)
    assert detail.workflow.status == WorkflowStatus.completed
    assert [step.tool_name for step in detail.plan.steps] == ["case_lookup", "priority_classifier", "sla_checker"]
    assert all(isinstance(result, ToolExecutionResult) for result in detail.tool_results)
    priority = next(result for result in detail.tool_results if result.tool_name == "priority_classifier")
    assert priority.payload["priority"] == "High"
    assert json.loads(detail.model_dump_json())["workflow"]["status"] == "completed"


def test_tool_result_normalization_preserves_unmodeled_payload_fields(orchestrator: Orchestrator) -> None:
    tasks, _, _ = _services(orchestrator)

    detail = tasks.start_task(StartTaskRequest(user_request="Review CASE-220."))
    result = next(item for item in detail.tool_results if item.tool_name == "case_lookup")

    assert result.payload["case_id"] == "CASE-220"
    assert result.payload["customer_message"] == "Please refund the duplicate charge."
    assert result.payload["purchase_age_days"] == 7
    assert "_latency_ms" in result.payload


def test_waiting_task_has_typed_pending_approval_and_persisted_state(orchestrator: Orchestrator) -> None:
    tasks, approvals, _ = _services(orchestrator)

    detail = tasks.start_task(StartTaskRequest(user_request=APPROVAL_TASK))
    pending = approvals.get_pending(detail.task_id)

    assert detail.workflow.status == WorkflowStatus.waiting_for_approval
    assert detail.workflow.waiting_for_approval is True
    assert isinstance(pending, PendingApproval)
    assert pending.step_id == detail.workflow.current_step_id
    assert pending.tool_name == "generate_report"
    assert orchestrator.repo.get_task(detail.task_id)["status"] == "waiting_for_approval"
    assert json.loads(pending.model_dump_json())["task_id"] == detail.task_id


def test_approval_service_approve_preserves_current_global_approval_semantics(
    orchestrator: Orchestrator,
    isolated_report_dir: Path,
) -> None:
    tasks, approvals, _ = _services(orchestrator)
    waiting = tasks.start_task(StartTaskRequest(user_request=APPROVAL_TASK))

    completed = approvals.approve(waiting.task_id, "Phase 2 reviewer approval")

    assert completed.workflow.status == WorkflowStatus.completed
    assert completed.approval_status == "approved"
    assert completed.customer_response
    assert Path(completed.generated_report_path).parent == isolated_report_dir
    assert [step.status.value for step in completed.plan.steps[-2:]] == ["completed", "completed"]
    assert isinstance(completed.approvals[0], ApprovalRecord)
    assert completed.approvals[0].reviewer_note == "Phase 2 reviewer approval"


def test_approval_service_reject_preserves_report_and_skipped_response(
    orchestrator: Orchestrator,
    isolated_report_dir: Path,
) -> None:
    tasks, approvals, _ = _services(orchestrator)
    waiting = tasks.start_task(StartTaskRequest(user_request=APPROVAL_TASK))

    rejected = approvals.reject(waiting.task_id, "Phase 2 reviewer rejection")

    assert rejected.workflow.status == WorkflowStatus.rejected
    assert rejected.approval_status == "rejected"
    assert rejected.customer_response is None
    assert Path(rejected.generated_report_path).parent == isolated_report_dir
    assert [step.status.value for step in rejected.plan.steps[-2:]] == ["completed", "skipped"]
    assert rejected.approvals[0].decision == "rejected"


def test_services_reconstruct_completed_and_waiting_tasks_from_sqlite(orchestrator: Orchestrator) -> None:
    tasks, _, _ = _services(orchestrator)
    completed = tasks.start_task(StartTaskRequest(user_request="Review CASE-220."))
    waiting = tasks.start_task(StartTaskRequest(user_request=APPROVAL_TASK))

    reconstructed = Orchestrator(orchestrator.db, app_mode="local")
    reconstructed_tasks, reconstructed_approvals, reconstructed_history = _services(reconstructed)

    loaded_completed = reconstructed_tasks.get_task(completed.task_id)
    loaded_waiting = reconstructed_history.load_task_detail(waiting.task_id)
    approved = reconstructed_approvals.approve(waiting.task_id, "Approved after reconstruction")

    assert loaded_completed.workflow.status == WorkflowStatus.completed
    assert loaded_waiting.workflow.status == WorkflowStatus.waiting_for_approval
    assert loaded_waiting.pending_approval is not None
    assert approved.workflow.status == WorkflowStatus.completed


def test_history_service_returns_typed_search_steps_approvals_and_events(orchestrator: Orchestrator) -> None:
    tasks, approvals, history = _services(orchestrator)
    waiting = tasks.start_task(StartTaskRequest(user_request=APPROVAL_TASK))
    approvals.approve(waiting.task_id, "History audit note")

    rows = history.search_tasks(TaskHistoryQuery(task_id=waiting.task_id, limit=10))
    detail = history.load_task_detail(waiting.task_id)
    steps = history.steps(waiting.task_id)
    decisions = history.approvals(waiting.task_id)
    events = history.events(waiting.task_id)

    assert len(rows) == 1 and isinstance(rows[0], TaskSummary)
    assert rows[0].task_id == waiting.task_id
    assert [step.tool_name for step in steps][-2:] == ["generate_report", "generate_customer_response"]
    assert len(decisions) == 1 and isinstance(decisions[0], ApprovalRecord)
    assert decisions[0].reviewer_note == "History audit note"
    assert events and all(isinstance(event, AuditEventRecord) for event in events)
    assert {event.event_type for event in detail.events} >= {
        "task_received",
        "plan_generated",
        "plan_validated",
        "waiting_for_approval",
        "approval_received",
    }
    assert json.loads(rows[0].model_dump_json())["task_id"] == waiting.task_id


def test_demo_services_allow_deterministic_and_reject_llm_without_creating_task(tmp_path: Path) -> None:
    orchestrator = Orchestrator(Database(tmp_path / "demo.db"), app_mode="demo")
    tasks = TaskService(orchestrator)

    completed = tasks.start_task(StartTaskRequest(user_request="Review CASE-220."))

    assert completed.workflow.status == WorkflowStatus.completed
    assert tasks.provider_service.allowed_planner_modes() == (PlannerMode.deterministic,)
    with pytest.raises(InvalidTaskRequest, match="deterministic planning only"):
        tasks.start_task(
            StartTaskRequest(
                user_request="Review CASE-220.",
                planner_mode=PlannerMode.llm,
                provider=ProviderName.openai,
            )
        )
    assert len(orchestrator.repo.search_tasks(limit=10)) == 1


@pytest.mark.parametrize(
    ("provider", "effective_model", "requires_api_key"),
    [
        (ProviderName.openai, "gpt-4.1-mini", True),
        (ProviderName.anthropic, "claude-3-5-haiku-latest", True),
        (ProviderName.gemini, "gemini-2.0-flash", True),
        (ProviderName.ollama, "llama3.2", False),
    ],
)
def test_local_provider_configuration_is_framework_neutral_and_offline(
    provider: ProviderName,
    effective_model: str,
    requires_api_key: bool,
) -> None:
    service = ProviderService("local")

    configuration = service.configure(
        StartTaskRequest(user_request="Review CASE-220.", planner_mode=PlannerMode.llm, provider=provider)
    )

    assert configuration.effective_provider == provider
    assert configuration.effective_model == effective_model
    assert configuration.requires_api_key is requires_api_key
    assert service.allowed_planner_modes() == (PlannerMode.deterministic, PlannerMode.llm)


def test_api_key_is_passed_only_to_orchestrator_and_never_returned_or_persisted(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "phase2-test-secret-that-must-not-leak"
    observed: dict[str, str | None] = {}

    def mocked_provider(provider, prompt, api_key=None, model=None, output_schema=None):
        observed["api_key"] = api_key
        return _llm_case_plan()

    monkeypatch.setattr("src.planners.llm_planner.generate_text", mocked_provider)
    tasks = TaskService(orchestrator)

    detail = tasks.start_task(
        StartTaskRequest(
            user_request="Review CASE-220.",
            planner_mode=PlannerMode.llm,
            provider=ProviderName.openai,
            model="test-only-model",
        ),
        api_key=secret,
    )
    persisted = orchestrator.repo.get_task(detail.task_id)
    serialized = detail.model_dump_json()

    assert observed["api_key"] == secret
    assert detail.workflow.status == WorkflowStatus.completed
    assert secret not in serialized
    assert "api_key" not in serialized
    assert secret not in persisted["state_json"]
    assert "api_key" not in persisted["state"]


def test_service_error_taxonomy_maps_missing_tasks_and_invalid_approvals(orchestrator: Orchestrator) -> None:
    tasks, approvals, history = _services(orchestrator)
    completed = tasks.start_task(StartTaskRequest(user_request="Review CASE-220."))

    with pytest.raises(TaskNotFound) as missing:
        history.load_task_detail("TASK-MISSING")
    with pytest.raises(InvalidApproval) as invalid:
        approvals.approve(completed.task_id, "Already complete")

    assert missing.value.to_contract().code.value == "task_not_found"
    assert invalid.value.to_contract().code.value == "invalid_approval"
    assert json.loads(missing.value.to_contract().model_dump_json())["task_id"] == "TASK-MISSING"
