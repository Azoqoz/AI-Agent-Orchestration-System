from __future__ import annotations

from typing import Any
from src.agent.schemas import GenerateCustomerResponseInput
from src.reporting.response_builder import build_response


def execute(data: GenerateCustomerResponseInput, context: dict[str, Any]) -> dict[str, Any]:
    state = context["state"]
    if data.task_id != state["task_id"]: raise ValueError("Response task ID does not match workflow state")
    return {"customer_response":build_response(state),"dispatched":False}

