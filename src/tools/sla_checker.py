from __future__ import annotations

from datetime import datetime
from typing import Any
from src.agent.schemas import SLACheckerInput
from src.config import DEMO_NOW


def execute(data: SLACheckerInput, context: dict[str, Any]) -> dict[str, Any]:
    case = context["repo"].one("cases", data.case_id.upper())
    if not case: raise ValueError(f"Case {data.case_id} was not found")
    priority = data.priority or "Medium"
    with context["db"].connect() as conn:
        row = conn.execute("SELECT hours FROM sla_rules WHERE priority=?",(priority,)).fetchone()
    allowed = int(row["hours"] if row else 48)
    elapsed = round((datetime.fromisoformat(DEMO_NOW)-datetime.fromisoformat(case["created_at"])).total_seconds()/3600,2)
    remaining = round(allowed-elapsed,2); breached = remaining < 0
    explanation = f"{elapsed:.1f} hours elapsed against a {allowed}-hour {priority.lower()} priority SLA"
    return {"priority":priority,"allowed_sla_hours":allowed,"elapsed_hours":elapsed,"remaining_hours":remaining,
            "breached":breached,"explanation":explanation + ("; SLA breached." if breached else "; within SLA.")}

