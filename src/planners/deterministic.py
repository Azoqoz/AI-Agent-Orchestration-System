from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.agent.schemas import ExecutionPlan, PlanStep
from src.planners.base import Planner


UNSUPPORTED_ACTION_MESSAGE = (
    "This action is not supported in V1. The agent can review customer/case data, evaluate policies, "
    "calculate recommendations, generate reports, and draft customer responses, but it cannot modify "
    "customer or case records or send external messages."
)

MISSING_REFUND_CASE_MESSAGE = (
    "A case ID is required to calculate a refund. Please provide one of the available CASE IDs "
    "from the Demo Data Guide."
)


class UnsupportedActionError(ValueError):
    def __init__(self, actions: list[str]) -> None:
        super().__init__(UNSUPPORTED_ACTION_MESSAGE)
        self.user_message = UNSUPPORTED_ACTION_MESSAGE
        self.unsupported_actions = actions


UNSUPPORTED_ACTION_PATTERNS = (
    ("delete customer", r"\b(?:delete|remove|erase)\s+(?:the\s+)?customer\b"),
    ("modify customer", r"\b(?:create|modify|update|edit|change)\s+(?:the\s+|a\s+)?(?:customer|customer record|account record)\b"),
    ("close case", r"\bclos(?:e|ing)\s+(?:the\s+)?(?:case\b|case-\d{3,}\b)"),
    ("reopen case", r"\breopen(?:ing)?\s+(?:the\s+)?(?:case\b|case-\d{3,}\b)"),
    ("update case", r"\bupdat(?:e|ing)\s+(?:the\s+)?(?:case\b|case-\d{3,}\b)"),
    ("modify case", r"\b(?:modif(?:y|ying)|edit(?:ing)?)\s+(?:the\s+)?(?:case\b|case-\d{3,}\b)"),
    ("change case status", r"\bchang(?:e|ing)\s+(?:the\s+)?(?:(?:case\b|case-\d{3,}\b)(?:'s)?\s+status|status\s+(?:of|for)\s+(?:the\s+)?(?:case\b|case-\d{3,}\b))"),
    ("resolve case", r"\bresolv(?:e|ing)\s+(?:the\s+)?(?:case\b|case-\d{3,}\b)"),
    ("delete case", r"\b(?:delete|remove|erase)\s+(?:the\s+)?(?:case\b|case-\d{3,}\b)"),
    ("assign case", r"\b(?:assign|reassign)(?:ing)?\s+(?:the\s+)?(?:case\b|case-\d{3,}\b)"),
    ("create or update CRM record", r"\b(?:create|update|modify|delete)\s+(?:a\s+|the\s+)?(?:crm|crm record)\b"),
    ("send email", r"\b(?:send|dispatch|deliver)\s+(?:an?\s+|the\s+)?email\b|\bemail\s+(?:the\s+)?customer\b"),
    ("send SMS", r"\b(?:send|dispatch)\s+(?:an?\s+|the\s+)?(?:sms|text message)\b"),
    ("execute payment", r"\b(?:execute|process|issue|transfer)\s+(?:a\s+|the\s+)?payment\b"),
    ("execute refund", r"\b(?:execute|process|issue|transfer)\s+(?:a\s+|the\s+)?refund\b"),
    ("cancel order", r"\b(?:cancel|void)\s+(?:an?\s+|the\s+)?order\b"),
    ("database mutation", r"\b(?:delete\s+from|insert\s+into|drop\s+table|update\s+database|database\s+mutation|write\s+to\s+(?:the\s+)?database)\b"),
    ("shell or system action", r"\b(?:run|execute)\s+(?:a\s+|the\s+)?(?:shell|system|terminal|powershell|bash)\s*(?:command|action)?\b"),
)


def unsupported_actions(request: str) -> list[str]:
    lower = request.lower()
    return [label for label, pattern in UNSUPPORTED_ACTION_PATTERNS if re.search(pattern, lower)]


@dataclass(frozen=True)
class Intent:
    name: str
    patterns: tuple[str, ...]


class DeterministicPlanner(Planner):
    """Explainable intent/entity planner for the offline workflow."""
    intents = (
      Intent("customer_lookup",("customer","account","subscription")),
      Intent("case_lookup",("case","complaint","refund request")),
      Intent("policy_checker",("eligib","policy","allowed","refund")),
      Intent("refund_calculator",("refund amount","calculate","calculation","total","refund")),
      Intent("priority_classifier",("urgent","priority","severity")),
      Intent("sla_checker",("sla","overdue","delayed","waiting")),
      Intent("generate_report",("report","internal report")),
      Intent("generate_customer_response",("reply","response","message to customer","prepare a customer")),
      Intent("task_history_search",("last case","previous task","history","recent","most recent")),
    )

    def create_plan(self, request: str) -> ExecutionPlan:
        text = request.strip()
        if not text: raise ValueError("Enter a business task before running the agent")
        blocked = unsupported_actions(text)
        if blocked: raise UnsupportedActionError(blocked)
        lower = text.lower()
        case_match = re.search(r"\bCASE-\d{3,}\b", text, re.I)
        cust_match = re.search(r"\bCUST-\d{3,}\b", text, re.I)
        case_id = case_match.group(0).upper() if case_match else None
        customer_id = cust_match.group(0).upper() if cust_match else None
        excluded = self.negative_constraints(lower)
        history_requested = any(p in lower for p in ("last case", "previous task", "history", "recent", "most recent"))
        if history_requested and not case_id and not customer_id:
            selected = {"task_history_search"}
        else:
            selected: set[str] = set()
            if case_id: selected.add("case_lookup")
            if customer_id or any(p in lower for p in ("customer", "account", "subscription", "open cases")):
                selected.add("customer_lookup")
            if any(p in lower for p in ("eligib", "policy", "manual review", "needs review")):
                selected.add("policy_checker")
            refund_requested = bool(re.search(r"(?:calculat\w*|determin\w*)\s+(?:the\s+|a\s+)?refund|refund\s+(?:amount|recommendation|calculation)", lower))
            if refund_requested and "refund_calculator" not in excluded and customer_id and not case_id:
                raise ValueError(MISSING_REFUND_CASE_MESSAGE)
            if refund_requested and "refund_calculator" not in excluded:
                selected.add("refund_calculator")
            if any(p in lower for p in ("urgent", "priority", "severity")):
                selected.add("priority_classifier")
            if any(p in lower for p in ("sla", "overdue", "delayed", "waiting")):
                selected.add("sla_checker")
            if any(p in lower for p in ("report", "internal report")) and "generate_report" not in excluded:
                selected.add("generate_report")
            if any(p in lower for p in ("reply", "response", "message to customer", "prepare a customer")) and "generate_customer_response" not in excluded:
                selected.add("generate_customer_response")

            # Minimal required dependencies.
            if "refund_calculator" in selected: selected.add("policy_checker")
            if case_id and selected & {"policy_checker", "refund_calculator", "priority_classifier", "sla_checker", "generate_report", "generate_customer_response"}:
                selected.add("case_lookup")
            if case_id and selected & {"generate_report", "generate_customer_response"}:
                selected.add("customer_lookup")
            # A requested refund decision followed by a response needs an auditable report.
            if {"refund_calculator", "generate_customer_response"} <= selected and "generate_report" not in excluded and "response_only" not in excluded:
                selected.add("generate_report")

            selected.difference_update(excluded & {"refund_calculator", "generate_report", "generate_customer_response"})
        if not selected: raise ValueError("This request is unsupported or ambiguous. Include a customer/case ID and an operation such as eligibility, refund, priority, SLA, response, report, or history.")
        if selected - {"task_history_search"} and not (case_id or customer_id):
            raise ValueError("The request needs a customer ID (CUST-###) or case ID (CASE-###)")
        order = ["case_lookup","customer_lookup","policy_checker","priority_classifier","sla_checker","refund_calculator","generate_report","generate_customer_response","task_history_search"]
        steps: list[PlanStep] = []
        for tool in order:
            if tool not in selected: continue
            inputs, deps = self._inputs(tool, case_id, customer_id, steps, lower)
            steps.append(PlanStep(step_id=f"step_{len(steps)+1}",tool_name=tool,
                description=self._description(tool),reason=self._reason(tool),inputs=inputs,depends_on=deps,
                requires_approval=(tool == "generate_report" or
                                   (tool == "generate_customer_response" and "refund_calculator" in selected))))
        task_type = "history_search" if selected == {"task_history_search"} else "customer_operations"
        return ExecutionPlan(task_type=task_type,planner_mode="deterministic",summary=f"Execute {len(steps)} validated customer-operations step(s).",steps=steps)

    @staticmethod
    def negative_constraints(lower: str) -> set[str]:
        excluded: set[str] = set()
        if re.search(r"(?:without|do not|don't|no)\s+(?:calculat\w*\s+)?(?:a\s+|the\s+)?refund", lower):
            excluded.add("refund_calculator")
            if "response" in lower and "report" not in lower:
                excluded.add("generate_report")
        if re.search(r"(?:no|without|do not|don't)\s+(?:generate\s+|generating\s+)?(?:an?\s+)?(?:internal\s+)?report", lower):
            excluded.add("generate_report")
        if re.search(r"(?:no|without|do not|don't)\s+(?:generate\s+|generating\s+)?(?:a\s+)?(?:customer\s+)?response", lower):
            excluded.add("generate_customer_response")
        if "response only" in lower or "customer response only" in lower:
            excluded.update({"response_only", "generate_report"})
        if "report only" in lower or "internal report only" in lower:
            excluded.add("generate_customer_response")
        return excluded

    def _inputs(self, tool: str, case_id: str | None, customer_id: str | None, steps: list[PlanStep], lower: str) -> tuple[dict[str,Any],list[str]]:
        by_name = {s.tool_name:s.step_id for s in steps}
        if tool == "case_lookup": return ({"case_id":case_id,"customer_id":customer_id} if customer_id else {"case_id":case_id}), []
        if tool == "customer_lookup":
            return ({"customer_id":customer_id},[]) if customer_id else ({"customer_id":"$case_lookup.customer_id"},[by_name["case_lookup"]])
        if tool in {"policy_checker","priority_classifier"}: return {"case_id":case_id}, [by_name["case_lookup"]]
        if tool == "sla_checker":
            deps=[by_name["case_lookup"]]; inputs={"case_id":case_id}
            if "priority_classifier" in by_name: deps.append(by_name["priority_classifier"]); inputs["priority"]="$priority_classifier.priority"
            return inputs,deps
        if tool == "refund_calculator": return {"amount_paid":"$policy_checker.amount_paid","refund_percentage":"$policy_checker.recommended_refund_percentage","non_refundable_fee":"$policy_checker.non_refundable_fee","previous_refund_amount":"$policy_checker.previous_refund_amount"},[by_name["policy_checker"]]
        if tool == "generate_report": return {"task_id":"$task_id"}, list(by_name.values())
        if tool == "generate_customer_response": return {"task_id":"$task_id"}, [by_name.get("generate_report",next(reversed(by_name.values())))]
        if tool == "task_history_search": return {"status":"completed" if "approved" in lower else None,"keyword":"refund" if "refund" in lower else None,"limit":10},[]
        return {},[]

    @staticmethod
    def _description(tool: str) -> str: return tool.replace("_"," ").capitalize()
    @staticmethod
    def _reason(tool: str) -> str:
        return {"case_lookup":"Load the referenced case facts.","customer_lookup":"Load the related customer context.",
          "policy_checker":"Apply the deterministic refund policy.","refund_calculator":"Calculate the explainable recommended amount.",
          "priority_classifier":"Assess urgency using public rules.","sla_checker":"Compare elapsed time with the configured SLA.",
          "generate_report":"Create the persistent internal audit report after approval.",
          "generate_customer_response":"Draft a safe customer response after approval.","task_history_search":"Search prior persisted tasks."}[tool]
