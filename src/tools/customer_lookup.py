from __future__ import annotations

from typing import Any
from src.agent.schemas import CustomerLookupInput


def execute(data: CustomerLookupInput, context: dict[str, Any]) -> dict[str, Any]:
    row = context["repo"].one("customers", data.customer_id.upper())
    if not row: raise ValueError(f"Customer {data.customer_id} was not found")
    customer_id = row.pop("id")
    return {"customer_id": customer_id, **row, "open_cases": context["repo"].open_cases_for_customer(customer_id)}
