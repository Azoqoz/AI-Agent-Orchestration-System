from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.agent.schemas import StepStatus, TaskId


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlannerMode(str, Enum):
    deterministic = "deterministic"
    llm = "llm"


class ProviderName(str, Enum):
    openai = "openai"
    anthropic = "anthropic"
    gemini = "gemini"
    ollama = "ollama"


class WorkflowStatus(str, Enum):
    received = "received"
    plan_generated = "plan_generated"
    running = "running"
    waiting_for_approval = "waiting_for_approval"
    finalizing = "finalizing"
    completed = "completed"
    rejected = "rejected"
    failed = "failed"


class ServiceErrorCode(str, Enum):
    task_not_found = "task_not_found"
    invalid_task_request = "invalid_task_request"
    approval_required = "approval_required"
    invalid_approval = "invalid_approval"
    planner_unavailable = "planner_unavailable"
    provider_unavailable = "provider_unavailable"
    workflow_execution_error = "workflow_execution_error"


class StartTaskRequest(ContractModel):
    user_request: str
    planner_mode: PlannerMode = PlannerMode.deterministic
    provider: ProviderName | None = None
    model: str | None = None


class ResumeApprovalRequest(ContractModel):
    decision: Literal["approved", "rejected"]
    reviewer_note: str | None = None


class PlannerConfiguration(ContractModel):
    app_mode: Literal["demo", "local"]
    planner_mode: PlannerMode
    provider: ProviderName | None = None
    effective_provider: ProviderName | None = None
    requested_model: str | None = None
    effective_model: str | None = None
    requires_api_key: bool = False


class WorkflowStatusDTO(ContractModel):
    status: WorkflowStatus
    current_step_id: str | None = None
    is_terminal: bool
    waiting_for_approval: bool


class PlanStepDTO(ContractModel):
    step_id: str
    tool_name: str
    description: str
    reason: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    status: StepStatus


class ExecutionPlanDTO(ContractModel):
    task_type: str
    planner_mode: PlannerMode
    summary: str
    steps: list[PlanStepDTO] = Field(default_factory=list)


class ToolExecutionResult(ContractModel):
    step_id: str | None = None
    tool_name: str
    status: StepStatus
    payload: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int | None = None
    error_message: str | None = None


class PendingApproval(ContractModel):
    task_id: TaskId
    step_id: str
    tool_name: str
    description: str
    reason: str
    recommended_action: str | None = None


class ApprovalRecord(ContractModel):
    id: int | None = None
    task_id: TaskId
    step_id: str
    decision: Literal["approved", "rejected"]
    reviewer_note: str | None = None
    decided_at: str


class AuditEventRecord(ContractModel):
    id: int | None = None
    task_id: TaskId
    step_id: str | None = None
    event_type: str
    detail: str | None = None
    created_at: str


class ServiceErrorDTO(ContractModel):
    code: ServiceErrorCode
    message: str
    task_id: TaskId | None = None
    retryable: bool = False


class TaskSummary(ContractModel):
    task_id: TaskId
    user_request: str
    planner_mode: PlannerMode
    provider: ProviderName | None = None
    status: WorkflowStatus
    created_at: str
    updated_at: str
    completed_at: str | None = None
    tools_used: int = 0
    requested_planner: str | None = None
    executed_planner: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    case_id: str | None = None
    customer_id: str | None = None
    refund_amount: str | None = None
    approval_status: Literal["approved", "rejected"] | None = None


class TaskDetail(ContractModel):
    task_id: TaskId
    user_request: str
    planner_mode: PlannerMode
    provider: ProviderName | None = None
    model: str | None = None
    workflow: WorkflowStatusDTO
    plan: ExecutionPlanDTO | None = None
    tool_results: list[ToolExecutionResult] = Field(default_factory=list)
    pending_approval: PendingApproval | None = None
    approvals: list[ApprovalRecord] = Field(default_factory=list)
    events: list[AuditEventRecord] = Field(default_factory=list)
    approval_status: Literal["approved", "rejected"] | None = None
    approval_reason: str | None = None
    recommended_action: str | None = None
    final_response: str | None = None
    generated_report_path: str | None = None
    customer_response: str | None = None
    requested_planner: str
    executed_planner: str
    fallback_used: bool = False
    fallback_reason: str | None = None
    planning_notice: str | None = None
    unsupported_actions: list[str] = Field(default_factory=list)
    error: ServiceErrorDTO | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class TaskHistoryQuery(ContractModel):
    task_id: TaskId | None = None
    case_id: str | None = None
    customer_id: str | None = None
    status: WorkflowStatus | None = None
    keyword: str | None = None
    limit: int = Field(default=10, ge=1, le=50)
