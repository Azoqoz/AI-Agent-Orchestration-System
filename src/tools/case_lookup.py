from __future__ import annotations

from datetime import datetime
from typing import Any

from src.agent.schemas import CaseLookupInput
from src.config import DEMO_NOW


def execute(data: CaseLookupInput, context: dict[str, Any]) -> dict[str, Any]:
    row = context["repo"].one("cases", data.case_id.upper())
    if not row: raise ValueError(f"Case {data.case_id} was not found")
    if data.customer_id and row["customer_id"] != data.customer_id.upper():
        raise ValueError(f"Case {data.case_id} does not belong to {data.customer_id}")
    result = {"case_id": row.pop("id"), **row}
    order = context["repo"].one("orders", row["order_id"]) if row.get("order_id") else None
    if order:
        result.update({
            "amount_paid": order.get("amount_paid"),
            "purchase_date": order.get("purchase_date"),
            "usage_percent": order.get("usage_percent"),
        })
        if order.get("purchase_date"):
            result["purchase_age_days"] = (
                datetime.fromisoformat(DEMO_NOW).date()
                - datetime.fromisoformat(order["purchase_date"]).date()
            ).days
    return result
