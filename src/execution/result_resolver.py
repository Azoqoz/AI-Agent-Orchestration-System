from __future__ import annotations

from typing import Any


def recommendation(results: dict[str,Any]) -> str:
    policy=results.get("policy_checker",{}); refund=results.get("refund_calculator",{})
    if not policy and not refund: return "Review the available case context before proceeding."
    eligibility=policy.get("eligibility","Unknown")
    if eligibility == "Eligible" and refund.get("final_recommended_refund") is not None:
        return f"Approve the recommended ${refund['final_recommended_refund']} USD refund after human review."
    if eligibility == "Eligible": return "Review the available policy context; no financial recommendation was calculated."
    if eligibility == "Manual Review": return "Escalate the recommendation for manual policy review."
    return "Do not approve a refund under the current policy."
