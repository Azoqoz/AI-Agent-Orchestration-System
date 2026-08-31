from __future__ import annotations

from src.services.contracts import PendingApproval, ResumeApprovalRequest, TaskDetail
from src.services.errors import ApprovalRequired
from src.services.task_service import TaskService


class ApprovalService:
    """Expose the current task-global approval semantics without redesigning them.

    One approval authorizes all remaining approval-marked steps. Rejection still
    generates the internal audit report and skips the customer response.
    """

    def __init__(self, task_service: TaskService) -> None:
        self.task_service = task_service

    def get_pending(self, task_id: str) -> PendingApproval | None:
        return self.task_service.get_task(task_id).pending_approval

    def require_pending(self, task_id: str) -> PendingApproval:
        pending = self.get_pending(task_id)
        if pending is None:
            raise ApprovalRequired("Task is not waiting for approval", task_id)
        return pending

    def approve(self, task_id: str, reviewer_note: str | None = None) -> TaskDetail:
        return self.task_service.resume_task(
            task_id,
            ResumeApprovalRequest(decision="approved", reviewer_note=reviewer_note),
        )

    def reject(self, task_id: str, reviewer_note: str | None = None) -> TaskDetail:
        return self.task_service.resume_task(
            task_id,
            ResumeApprovalRequest(decision="rejected", reviewer_note=reviewer_note),
        )
