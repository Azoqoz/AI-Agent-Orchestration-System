from __future__ import annotations

from decimal import Decimal
from typing import Any
from src.agent.schemas import PriorityClassifierInput


def execute(data: PriorityClassifierInput, context: dict[str, Any]) -> dict[str, Any]:
    repo = context["repo"]
    case = repo.one("cases", data.case_id.upper())
    if not case: raise ValueError(f"Case {data.case_id} was not found")
    customer = repo.one("customers", case["customer_id"]) if case.get("customer_id") else None
    order = repo.one("orders", case["order_id"]) if case.get("order_id") else None
    score, reasons = 0, []
    if order and Decimal(order["amount_paid"]) >= 500: score += 2; reasons.append("high-value request")
    if customer and customer["tier"] == "Platinum": score += 1; reasons.append("Platinum customer")
    if any(w in (case["customer_message"]+" "+case["description"]).lower() for w in ("urgent","angry","still waiting","blocking")): score += 2; reasons.append("urgent or negative wording")
    if case["previous_contacts"] >= 3: score += 2; reasons.append("repeated contacts")
    if customer and customer["account_status"] != "active": score += 1; reasons.append("inactive account")
    priority = "High" if score >= 4 else "Medium" if score >= 2 else "Low"
    return {"priority":priority,"score":score,"reasons":reasons or ["no elevated priority factors"]}

