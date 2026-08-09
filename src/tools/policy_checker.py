from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from src.agent.schemas import PolicyCheckInput
from src.config import DEMO_NOW


def execute(data: PolicyCheckInput, context: dict[str, Any]) -> dict[str, Any]:
    case = context["repo"].one("cases", data.case_id.upper())
    if not case: raise ValueError(f"Case {data.case_id} was not found")
    if not case.get("order_id"):
        return result("Manual Review","Missing order information","0",True)
    order = context["repo"].one("orders", case["order_id"])
    if not order or not order.get("purchase_date") or order.get("usage_percent") is None:
        return result("Manual Review","Missing or conflicting purchase information","0",True)
    age = (datetime.fromisoformat(DEMO_NOW).date() - datetime.fromisoformat(order["purchase_date"]).date()).days
    usage = Decimal(order["usage_percent"])
    facts = {"amount_paid":order["amount_paid"], "non_refundable_fee":order["non_refundable_fee"],
             "previous_refund_amount":order["previous_refund_amount"]}
    if order["already_refunded"]:
        return {**result("Not Eligible","The order was already refunded","0",False), **facts}
    if usage > Decimal("50"):
        return {**result("Not Eligible","Usage is greater than 50%","0",False), **facts}
    if age > 30:
        return {**result("Not Eligible","Purchase is older than 30 days","0",False), **facts}
    if age <= 14 and usage <= Decimal("10"):
        return {**result("Eligible","Purchase is within 14 days and usage is at most 10%","100",False), **facts}
    if 15 <= age <= 30 and usage <= Decimal("25"):
        return {**result("Manual Review","Purchase is 15-30 days old with usage at most 25%","75",True), **facts}
    return {**result("Not Eligible","The request does not meet the standard refund thresholds","0",False), **facts}


def result(eligibility: str, reason: str, percent: str, human: bool) -> dict[str, Any]:
    return {"eligibility":eligibility,"applicable_policy":"Standard refund policy v1","reason":reason,
            "recommended_refund_percentage":percent,"human_review_required":human}
