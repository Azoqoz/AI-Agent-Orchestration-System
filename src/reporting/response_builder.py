from __future__ import annotations

from typing import Any


def _find(results: dict[str, Any], name: str) -> dict[str, Any]:
    return next((v for k,v in results.items() if k.startswith(name+":") or k == name), {})


def build_case_summary(case: dict[str, Any]) -> str | None:
    """Summarize case lookup facts without making a policy or refund decision."""
    if not case.get("case_id"):
        return None
    status = str(case.get("status", "")).lower()
    case_type = str(case.get("case_type", "")).lower()
    customer_id = case.get("customer_id")
    description = str(case.get("description", "")).rstrip(".")
    subject = f"{status + ' ' if status else ''}{case_type + ' ' if case_type else ''}case".strip()
    article = "an" if subject[:1].lower() in "aeiou" else "a"
    summary = f"{case['case_id']} is {article} {subject}"
    if customer_id:
        summary += f" for customer {customer_id}"
    if description:
        summary += f" related to {description.lower()}"
    summary += "."

    order_facts: list[str] = []
    if case.get("amount_paid") not in (None, ""):
        order_facts.append(f"the related order amount is ${float(case['amount_paid']):,.2f}")
    if case.get("purchase_age_days") not in (None, ""):
        days = int(case["purchase_age_days"])
        order_facts.append(f"it was purchased {days} day{'s' if days != 1 else ''} ago")
    if case.get("usage_percent") not in (None, ""):
        order_facts.append(f"recorded usage is {float(case['usage_percent']):g}%")
    if order_facts:
        summary += " " + "; ".join(order_facts).capitalize() + "."
    return summary


def build_response(state: dict[str, Any]) -> str:
    results = state.get("tool_results", {})
    customer, case, policy = _find(results,"customer_lookup"), _find(results,"case_lookup"), _find(results,"policy_checker")
    refund, sla = _find(results,"refund_calculator"), _find(results,"sla_checker")
    name = customer.get("name","Customer").split()[0]
    greeting = f"Hello {name},"
    apology = " We’re sorry this response took longer than expected." if sla.get("breached") else ""
    if not policy and not refund:
        issue = case.get("description") or "your recent request"
        body = f"We reviewed your case regarding {issue.lower()} and prepared this response using the available case and account information."
    elif policy and not refund:
        body = "We reviewed your request against the available policy and case information. No financial recommendation was calculated or finalized."
    elif state.get("approval_status") == "rejected":
        body = "After review, we’re unable to approve the proposed refund recommendation. No refund has been processed."
    elif policy.get("eligibility") == "Eligible" and state.get("approval_status") == "approved":
        amount = refund.get("final_recommended_refund","0.00")
        body = f"We reviewed your request and approved a recommended refund of ${amount} USD. This is a draft recommendation; no funds have been transferred."
    elif policy.get("eligibility") == "Not Eligible":
        body = f"We reviewed your request and it does not meet the current refund policy because {policy.get('reason','the eligibility requirements were not met').lower()}. No refund has been processed."
    else:
        body = "Your request needs additional human review before a decision can be finalized. No refund has been processed."
    return f"{greeting}\n\n{body}{apology}\n\nKind regards,\nCustomer Operations"
