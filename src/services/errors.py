from __future__ import annotations

from src.services.contracts import ServiceErrorCode, ServiceErrorDTO


class ServiceError(Exception):
    code = ServiceErrorCode.workflow_execution_error
    retryable = False

    def __init__(self, message: str, task_id: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.task_id = task_id

    def to_contract(self) -> ServiceErrorDTO:
        return ServiceErrorDTO(
            code=self.code,
            message=self.message,
            task_id=self.task_id,
            retryable=self.retryable,
        )


class TaskNotFound(ServiceError):
    code = ServiceErrorCode.task_not_found


class InvalidTaskRequest(ServiceError):
    code = ServiceErrorCode.invalid_task_request


class ApprovalRequired(ServiceError):
    code = ServiceErrorCode.approval_required


class InvalidApproval(ServiceError):
    code = ServiceErrorCode.invalid_approval


class PlannerUnavailable(ServiceError):
    code = ServiceErrorCode.planner_unavailable
    retryable = True


class ProviderUnavailable(ServiceError):
    code = ServiceErrorCode.provider_unavailable
    retryable = True


class WorkflowExecutionError(ServiceError):
    code = ServiceErrorCode.workflow_execution_error
