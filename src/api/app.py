from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.agent.schemas import TaskId
from src.api.dependencies import ServiceContainer, get_service_container
from src.api.schemas import (
    CapabilitiesResponse,
    ErrorResponse,
    HealthResponse,
    ProviderCapability,
    ToolCapability,
)
from src.services import (
    ApprovalRecord,
    ApprovalRequired,
    AuditEventRecord,
    InvalidApproval,
    InvalidTaskRequest,
    PendingApproval,
    PlanStepDTO,
    PlannerUnavailable,
    ProviderUnavailable,
    ResumeApprovalRequest,
    ServiceError,
    ServiceErrorCode,
    ServiceErrorDTO,
    StartTaskRequest,
    TaskDetail,
    TaskHistoryQuery,
    TaskNotFound,
    TaskSummary,
    WorkflowExecutionError,
    WorkflowStatus,
)


DEFAULT_CORS_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class CORSSettings:
    allowed_origins: tuple[str, ...]
    allow_credentials: bool


def load_cors_settings() -> CORSSettings:
    configured = os.getenv("CORS_ALLOWED_ORIGINS")
    origins = tuple(item.strip() for item in configured.split(",") if item.strip()) if configured else DEFAULT_CORS_ORIGINS
    allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "false").strip().lower() in TRUE_VALUES
    if "*" in origins and allow_credentials:
        allow_credentials = False
    return CORSSettings(allowed_origins=origins, allow_credentials=allow_credentials)


HTTP_STATUS_BY_ERROR = {
    TaskNotFound: 404,
    InvalidTaskRequest: 400,
    ApprovalRequired: 409,
    InvalidApproval: 409,
    PlannerUnavailable: 400,
    ProviderUnavailable: 503,
    WorkflowExecutionError: 500,
}


def _service_error_status(error: ServiceError) -> int:
    return next(
        (status for error_type, status in HTTP_STATUS_BY_ERROR.items() if isinstance(error, error_type)),
        500,
    )


def create_app() -> FastAPI:
    application = FastAPI(title="AI Agent Orchestration API", version="1.0.0")
    cors = load_cors_settings()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors.allowed_origins),
        allow_credentials=cors.allow_credentials,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Provider-API-Key"],
    )

    @application.exception_handler(ServiceError)
    async def service_error_handler(request: Request, error: ServiceError) -> JSONResponse:
        body = ErrorResponse(error=error.to_contract())
        return JSONResponse(status_code=_service_error_status(error), content=body.model_dump(mode="json"))

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
        body = ErrorResponse(
            error=ServiceErrorDTO(
                code=ServiceErrorCode.invalid_task_request,
                message="Request validation failed.",
            )
        )
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @application.get("/capabilities", response_model=CapabilitiesResponse)
    def capabilities(services: Annotated[ServiceContainer, Depends(get_service_container)]) -> CapabilitiesResponse:
        provider_capabilities = [
            ProviderCapability(
                name=configuration.effective_provider,
                default_model=configuration.effective_model,
                requires_api_key=configuration.requires_api_key,
            )
            for configuration in services.providers.available_provider_configurations()
            if configuration.effective_provider and configuration.effective_model
        ]
        registry = services.tasks.orchestrator.registry
        tools = [
            ToolCapability(
                name=name,
                description=registry.get(name).description,
                requires_approval=registry.get(name).requires_approval,
            )
            for name in sorted(registry.names())
        ]
        return CapabilitiesResponse(
            app_mode=services.providers.app_mode,
            planner_modes=list(services.providers.allowed_planner_modes()),
            providers=provider_capabilities,
            tools=tools,
            approval_required_tools=[tool.name for tool in tools if tool.requires_approval],
        )

    @application.post("/tasks", response_model=TaskDetail)
    def start_task(
        task_request: StartTaskRequest,
        services: Annotated[ServiceContainer, Depends(get_service_container)],
        provider_api_key: Annotated[str | None, Header(alias="X-Provider-API-Key")] = None,
    ) -> TaskDetail:
        return services.tasks.start_task(task_request, api_key=provider_api_key)

    @application.get("/tasks", response_model=list[TaskSummary])
    def task_history(
        services: Annotated[ServiceContainer, Depends(get_service_container)],
        status: WorkflowStatus | None = None,
        case_id: str | None = None,
        customer_id: str | None = None,
        keyword: str | None = None,
        limit: Annotated[int, Query(ge=1, le=50)] = 10,
    ) -> list[TaskSummary]:
        return services.history.search_tasks(
            TaskHistoryQuery(
                status=status,
                case_id=case_id,
                customer_id=customer_id,
                keyword=keyword,
                limit=limit,
            )
        )

    @application.get("/tasks/{task_id}", response_model=TaskDetail)
    def task_detail(
        task_id: TaskId,
        services: Annotated[ServiceContainer, Depends(get_service_container)],
    ) -> TaskDetail:
        return services.tasks.get_task(task_id)

    @application.get("/tasks/{task_id}/approval", response_model=PendingApproval)
    def pending_approval(
        task_id: TaskId,
        services: Annotated[ServiceContainer, Depends(get_service_container)],
    ) -> PendingApproval:
        return services.approvals.require_pending(task_id)

    @application.post("/tasks/{task_id}/approval", response_model=TaskDetail)
    def decide_approval(
        task_id: TaskId,
        approval: ResumeApprovalRequest,
        services: Annotated[ServiceContainer, Depends(get_service_container)],
    ) -> TaskDetail:
        if approval.decision == "approved":
            return services.approvals.approve(task_id, approval.reviewer_note)
        return services.approvals.reject(task_id, approval.reviewer_note)

    @application.get("/tasks/{task_id}/events", response_model=list[AuditEventRecord])
    def task_events(
        task_id: TaskId,
        services: Annotated[ServiceContainer, Depends(get_service_container)],
    ) -> list[AuditEventRecord]:
        return services.history.events(task_id)

    @application.get("/tasks/{task_id}/steps", response_model=list[PlanStepDTO])
    def task_steps(
        task_id: TaskId,
        services: Annotated[ServiceContainer, Depends(get_service_container)],
    ) -> list[PlanStepDTO]:
        return services.history.steps(task_id)

    @application.get("/tasks/{task_id}/approvals", response_model=list[ApprovalRecord])
    def task_approvals(
        task_id: TaskId,
        services: Annotated[ServiceContainer, Depends(get_service_container)],
    ) -> list[ApprovalRecord]:
        return services.history.approvals(task_id)

    return application


app = create_app()
