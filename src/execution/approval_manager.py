from __future__ import annotations

from src.memory.repositories import Repository


def record_decision(repo: Repository, task_id: str, step_id: str, decision: str, reason: str | None) -> None:
    if decision not in {"approved","rejected"}: raise ValueError("Decision must be approved or rejected")
    repo.add_approval(task_id,step_id,decision,reason)

