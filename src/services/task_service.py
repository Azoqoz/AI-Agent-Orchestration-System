from __future__ import annotations

import json
from typing import Any

from src.agent.orchestrator import Orchestrator
from src.agent.schemas import StepStatus
from src.memory.repositories import Repository
from src.services.contracts import (
    ApprovalRecord,
    AuditEventRecord,
    ExecutionPlanDTO,
    PendingApproval,
    PlanStepDTO,
    PlannerMode,
    ProviderName,
    ResumeApprovalRequest,
    ServiceErrorCode,
    ServiceErrorDTO,
    StartTaskRequest,
    TaskDetail,
    ToolExecutionResult,
    WorkflowStatus,
    WorkflowStatusDTO,
)
from src.services.errors import (
    InvalidApproval,
    InvalidTaskRequest,
    TaskNotFound,
    WorkflowExecutionError,
)
from src.services.provider_service import ProviderService


TERMINAL_STATUSES = {
    WorkflowStatus.completed,
    WorkflowStatus.rejected,
    WorkflowStatus.failed,
}


def _json_value(value: Any) -> Any:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def _safe_error(state: dict[str, Any]) -> ServiceErrorDTO | None:
    if state.get("status") != "failed":
        return None
    message = state.get("display_error") or state.get("final_response") or "The workflow could not be completed."
    if state.get("failure_kind") == "unsupported_action":
        code = ServiceErrorCode.invalid_task_request
        retryable = False
    elif state.get("requested_planner") == "llm" and not state.get("plan"):
        lowered = message.lower()
        if any(term in lowered for term in ("provider", "ollama", "api key", "connect")):
            code = ServiceErrorCode.provider_unavailable
        else:
            code = ServiceErrorCode.planner_unavailable
        retryable = True
    else:
        code = ServiceErrorCode.workflow_execution_error
        retryable = False
    return ServiceErrorDTO(code=code, message=message, task_id=state.get("task_id"), retryable=retryable)


def _plan_from_state(state: dict[str, Any]) -> ExecutionPlanDTO | None:
    raw = state.get("plan") or {}
    if not raw:
        return None
    return ExecutionPlanDTO(
        task_type=raw["task_type"],
        planner_mode=raw["planner_mode"],
        summary=raw["summary"],
        steps=[PlanStepDTO.model_validate(step) for step in raw.get("steps", [])],
    )


def _tool_results(detail: dict[str, Any], state: dict[str, Any]) -> list[ToolExecutionResult]:
    results: list[ToolExecutionResult] = []
    persisted_tools: set[str] = set()
    for step in detail.get("steps") or []:
        output = _json_value(step.get("tool_output_json"))
        error = step.get("error_message")
        if output is None and not error:
            continue
        payload = output if isinstance(output, dict) else {"result": output}
        latency = step.get("latency_ms")
        if latency is None and isinstance(payload, dict):
            latency = payload.get("_latency_ms")
        results.append(
            ToolExecutionResult(
                step_id=step.get("step_id"),
                tool_name=step["tool_name"],
                status=step["status"],
                payload=payload,
                latency_ms=latency,
                error_message=error,
            )
        )
        persisted_tools.add(step["tool_name"])

    for tool_name, output in (state.get("tool_results") or {}).items():
        if tool_name in persisted_tools:
            continue
        payload = output if isinstance(output, dict) else {"result": output}
        results.append(
            ToolExecutionResult(
                tool_name=tool_name,
                status=StepStatus.completed,
                payload=payload,
                latency_ms=payload.get("_latency_ms") if isinstance(payload, dict) else None,
            )
        )
    return results


def build_task_detail(repo: Repository, task_id: str) -> TaskDetail:
    detail = repo.task_detail(task_id)
    if not detail:
        raise TaskNotFound(f"Task {task_id} was not found", task_id)
    state = detail.get("state") or {}
    status = WorkflowStatus(state.get("status", detail["status"]))
    plan = _plan_from_state(state)
    current_step_id = state.get("current_step_id")
    pending = None
    if status == WorkflowStatus.waiting_for_approval and plan and current_step_id:
        step = next((item for item in plan.steps if item.step_id == current_step_id), None)
        if step:
            pending = PendingApproval(
                task_id=task_id,
                step_id=step.step_id,
                tool_name=step.tool_name,
                description=step.description,
                reason=step.reason,
                recommended_action=state.get("recommended_action"),
            )

    approvals = [
        ApprovalRecord(
            id=item.get("id"),
            task_id=item["task_id"],
            step_id=item["step_id"],
            decision=item["decision"],
            reviewer_note=item.get("reason"),
            decided_at=item["decided_at"],
        )
        for item in detail.get("approvals") or []
    ]
    events = [
        AuditEventRecord(
            id=item.get("id"),
            task_id=item["task_id"],
            step_id=item.get("step_id"),
            event_type=item["event_type"],
            detail=item.get("detail"),
            created_at=item["created_at"],
        )
        for item in detail.get("events") or []
    ]

    provider = state.get("provider", detail.get("provider"))
    return TaskDetail(
        task_id=task_id,
        user_request=state.get("user_request", detail["user_request"]),
        planner_mode=PlannerMode(state.get("planner_mode", detail["planner_mode"])),
        provider=ProviderName(provider) if provider else None,
        model=state.get("model"),
        workflow=WorkflowStatusDTO(
            status=status,
            current_step_id=current_step_id,
            is_terminal=status in TERMINAL_STATUSES,
            waiting_for_approval=status == WorkflowStatus.waiting_for_approval,
        ),
        plan=plan,
        tool_results=_tool_results(detail, state),
        pending_approval=pending,
        approvals=approvals,
        events=events,
        approval_status=state.get("approval_status"),
        approval_reason=state.get("approval_reason"),
        recommended_action=state.get("recommended_action"),
        final_response=state.get("final_response", detail.get("final_response")),
        generated_report_path=state.get("generated_report_path", detail.get("report_path")),
        customer_response=state.get("customer_response", detail.get("customer_response")),
        requested_planner=state.get("requested_planner", detail["planner_mode"]),
        executed_planner=state.get("executed_planner", detail["planner_mode"]),
        fallback_used=bool(state.get("fallback_used", False)),
        fallback_reason=state.get("fallback_reason"),
        planning_notice=state.get("planning_notice"),
        unsupported_actions=list(state.get("unsupported_actions") or []),
        error=_safe_error(state),
        created_at=state.get("created_at", detail["created_at"]),
        updated_at=state.get("updated_at", detail["updated_at"]),
        completed_at=detail.get("completed_at"),
    )


class TaskService:
    """Synchronous framework-neutral facade over the existing orchestrator."""

    def __init__(self, orchestrator: Orchestrator, provider_service: ProviderService | None = None) -> None:
        self.orchestrator = orchestrator
        self.repo = orchestrator.repo
        self.provider_service = provider_service or ProviderService(orchestrator.app_mode)

    def start_task(self, request: StartTaskRequest, *, api_key: str | None = None) -> TaskDetail:
        self.provider_service.configure(request)
        try:
            state = self.orchestrator.start(
                request.user_request,
                request.planner_mode.value,
                request.provider.value if request.provider else None,
                api_key,
                request.model,
            )
        except ValueError as exc:
            raise InvalidTaskRequest(str(exc)) from exc
        except Exception as exc:
            raise WorkflowExecutionError("The task could not be started.") from exc
        return build_task_detail(self.repo, state["task_id"])

    def get_task(self, task_id: str) -> TaskDetail:
        return build_task_detail(self.repo, task_id)

    def resume_task(self, task_id: str, request: ResumeApprovalRequest) -> TaskDetail:
        try:
            self.orchestrator.resume(task_id, request.decision, request.reviewer_note)
        except ValueError as exc:
            message = str(exc)
            if "was not found" in message:
                raise TaskNotFound(message, task_id) from exc
            raise InvalidApproval(message, task_id) from exc
        except Exception as exc:
            raise WorkflowExecutionError("The task could not be resumed.", task_id) from exc
        return build_task_detail(self.repo, task_id)
