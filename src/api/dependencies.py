from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from src.agent.orchestrator import Orchestrator
from src.config import APP_MODE
from src.memory.database import Database
from src.services import ApprovalService, HistoryService, ProviderService, TaskService


@dataclass(frozen=True)
class ServiceContainer:
    tasks: TaskService
    approvals: ApprovalService
    history: HistoryService
    providers: ProviderService


def build_service_container(
    db: Database | None = None,
    app_mode: str = APP_MODE,
) -> ServiceContainer:
    orchestrator = Orchestrator(db=db, app_mode=app_mode)
    providers = ProviderService(orchestrator.app_mode)
    tasks = TaskService(orchestrator, provider_service=providers)
    return ServiceContainer(
        tasks=tasks,
        approvals=ApprovalService(tasks),
        history=HistoryService(orchestrator.repo),
        providers=providers,
    )


@lru_cache(maxsize=1)
def get_service_container() -> ServiceContainer:
    """Lazily construct process services; health checks do not call this."""
    return build_service_container()
