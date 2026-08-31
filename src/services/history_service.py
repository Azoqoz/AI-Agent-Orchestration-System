from __future__ import annotations

from src.memory.repositories import Repository
from src.services.contracts import (
    ApprovalRecord,
    AuditEventRecord,
    PlanStepDTO,
    ProviderName,
    TaskDetail,
    TaskHistoryQuery,
    TaskSummary,
)
from src.services.task_service import build_task_detail


class HistoryService:
    """Typed read facade over the existing SQLite repository."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def search_tasks(self, query: TaskHistoryQuery | None = None) -> list[TaskSummary]:
        query = query or TaskHistoryQuery()
        filters = query.model_dump(mode="json", exclude_none=True)
        rows = self.repo.search_tasks(**filters)
        return [
            TaskSummary(
                task_id=row["id"],
                user_request=row["user_request"],
                planner_mode=row["planner_mode"],
                provider=ProviderName(row["provider"]) if row.get("provider") else None,
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                completed_at=row.get("completed_at"),
                tools_used=row.get("tools_used", 0),
                requested_planner=row.get("requested_planner"),
                executed_planner=row.get("executed_planner"),
                fallback_used=bool(row.get("fallback_used", False)),
                fallback_reason=row.get("fallback_reason"),
                case_id=row.get("case_id"),
                customer_id=row.get("customer_id"),
                refund_amount=row.get("refund_amount"),
                approval_status=row.get("approval_status"),
            )
            for row in rows
        ]

    def load_task_detail(self, task_id: str) -> TaskDetail:
        return build_task_detail(self.repo, task_id)

    def steps(self, task_id: str) -> list[PlanStepDTO]:
        detail = self.load_task_detail(task_id)
        return detail.plan.steps if detail.plan else []

    def approvals(self, task_id: str) -> list[ApprovalRecord]:
        return self.load_task_detail(task_id).approvals

    def events(self, task_id: str) -> list[AuditEventRecord]:
        return self.load_task_detail(task_id).events
