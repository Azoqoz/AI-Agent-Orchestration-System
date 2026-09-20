from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Header

from src.agent.orchestrator import Orchestrator
from src.config import APP_MODE
from src.memory.database import Database
from src.services import ApprovalService, HistoryService, ProviderService, TaskService
from src.services.demo import DEMO_RETENTION_HOURS, validate_demo_session_id
from src.services.errors import InvalidTaskRequest


@dataclass(frozen=True)
class ServiceContainer:
    tasks: TaskService
    approvals: ApprovalService
    history: HistoryService
    providers: ProviderService


def build_service_container(
    db: Database | None = None,
    app_mode: str = APP_MODE,
    session_id: str | None = None,
) -> ServiceContainer:
    orchestrator = Orchestrator(db=db, app_mode=app_mode, session_id=session_id)
    if orchestrator.app_mode == "demo":
        orchestrator.repo.prune_expired_demo_tasks(DEMO_RETENTION_HOURS)
    providers = ProviderService(orchestrator.app_mode)
    tasks = TaskService(orchestrator, provider_service=providers)
    return ServiceContainer(
        tasks=tasks,
        approvals=ApprovalService(tasks),
        history=HistoryService(orchestrator.repo, app_mode=orchestrator.app_mode),
        providers=providers,
    )


@lru_cache(maxsize=1)
def _get_local_service_container() -> ServiceContainer:
    return build_service_container()


def get_service_container(
    demo_session_id: Annotated[str | None, Header(alias="X-Demo-Session-ID")] = None,
) -> ServiceContainer:
    """Resolve persistent local services or an isolated Demo Mode session."""
    if APP_MODE != "demo":
        return _get_local_service_container()
    try:
        session_id = validate_demo_session_id(demo_session_id)
    except ValueError as exc:
        raise InvalidTaskRequest(str(exc)) from exc
    return build_service_container(app_mode="demo", session_id=session_id)
