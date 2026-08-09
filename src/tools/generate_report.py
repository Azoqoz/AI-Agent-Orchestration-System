from __future__ import annotations

from typing import Any
from src.agent.schemas import GenerateReportInput
from src.reporting.report_builder import build_report


def execute(data: GenerateReportInput, context: dict[str, Any]) -> dict[str, Any]:
    state = context["state"]
    if data.task_id != state["task_id"]: raise ValueError("Report task ID does not match workflow state")
    md, txt, content = build_report(state)
    return {"markdown_path":md,"text_path":txt,"content":content}

