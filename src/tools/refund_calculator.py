from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from src.agent.schemas import RefundCalculatorInput


def execute(data: RefundCalculatorInput, context: dict[str, Any]) -> dict[str, Any]:
    amount, pct = data.amount_paid, data.refund_percentage
    fee, previous = data.non_refundable_fee, data.previous_refund_amount
    if min(amount,pct,fee,previous) < 0 or pct > 100: raise ValueError("Refund values must be non-negative and percentage at most 100")
    gross = (amount * pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    final = max(Decimal("0"), gross - fee - previous).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"gross_refundable_amount":f"{gross:.2f}","deducted_fees":f"{fee + previous:.2f}",
            "final_recommended_refund":f"{final:.2f}","currency":"USD",
            "calculation_explanation":f"{pct}% of {amount:.2f}, minus {fee:.2f} fee and {previous:.2f} previously refunded."}
