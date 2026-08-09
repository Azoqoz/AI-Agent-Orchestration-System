from __future__ import annotations

from typing import Any
from src.agent.schemas import TaskHistorySearchInput


def execute(data: TaskHistorySearchInput, context: dict[str, Any]) -> dict[str, Any]:
    rows = context["repo"].search_tasks(**data.model_dump(exclude_none=True))
    return {"count":len(rows),"tasks":rows}

