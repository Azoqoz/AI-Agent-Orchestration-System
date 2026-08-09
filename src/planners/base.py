from __future__ import annotations

from abc import ABC, abstractmethod
from src.agent.schemas import ExecutionPlan


class Planner(ABC):
    @abstractmethod
    def create_plan(self, request: str) -> ExecutionPlan: ...

