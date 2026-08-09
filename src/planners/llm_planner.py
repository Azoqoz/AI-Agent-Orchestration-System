from __future__ import annotations

import json
import re
from typing import Any

from src.agent.schemas import ExecutionPlan
from src.planners.base import Planner
from src.planners.deterministic import UnsupportedActionError, unsupported_actions
from src.providers import generate_text


class PlannerResponseError(ValueError):
    def __init__(self, message: str, provider: str, detail: str | None = None) -> None:
        super().__init__(detail or message)
        self.user_message = (
            "Ollama returned an invalid execution plan. Please retry or use Deterministic Planner."
            if provider.lower() == "ollama" else message
        )
        self.planning_invalid = True


def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _single_json_object(raw: str) -> dict[str, Any]:
    """Parse one object, allowing fences or non-JSON text but rejecting ambiguity."""
    text = _strip_code_fence(raw)
    try:
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("The planner response must be a JSON object")
        return value
    except json.JSONDecodeError:
        pass

    spans: list[str] = []
    start = None
    depth = 0
    in_string = False
    escaped = False
    malformed = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"' and depth:
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth == 0:
                malformed = True
                continue
            depth -= 1
            if depth == 0 and start is not None:
                spans.append(text[start:index + 1])
                start = None
    if depth or in_string or malformed or len(spans) != 1:
        raise ValueError("Expected exactly one complete top-level JSON object")
    value = json.loads(spans[0])
    if not isinstance(value, dict):
        raise ValueError("The planner response must be a JSON object")
    return value


class LLMPlanner(Planner):
    def __init__(self, provider: str, tool_descriptions: dict[str, Any], api_key: str | None = None, model: str | None = None,
                 known_entities: dict[str, str] | None = None) -> None:
        self.provider,self.tools,self.api_key,self.model=provider,tool_descriptions,api_key,model
        self.known_entities = known_entities or {}

    def create_plan(self, request: str) -> ExecutionPlan:
        blocked = unsupported_actions(request)
        if blocked:
            raise UnsupportedActionError(blocked)
        plan_schema = ExecutionPlan.model_json_schema()
        schema=json.dumps(plan_schema,indent=2)
        case_match = re.search(r"\bCASE-\d{3,}\b", request, re.I)
        customer_match = re.search(r"\bCUST-\d{3,}\b", request, re.I)
        entities = self.known_entities or {
            key: match.group(0).upper()
            for key, match in (("case_id", case_match), ("customer_id", customer_match))
            if match
        }
        entity_rules = json.dumps(entities) if entities else "No literal entity ID was detected."
        lower_request = request.lower()
        workflow_hint = ""
        if case_match and "refund" in lower_request and any(word in lower_request for word in ("response", "reply", "customer")):
            workflow_hint = (
                "Required workflow outline for this request: case_lookup -> customer_lookup -> policy_checker -> "
                "refund_calculator -> generate_report -> generate_customer_response. Include all six exactly once."
            )
        elif case_match and "priority" in lower_request and "sla" in lower_request:
            workflow_hint = (
                "Required workflow outline for this request: case_lookup -> priority_classifier -> sla_checker. "
                "Include all three exactly once."
            )
        elif case_match and "manual review" in lower_request:
            workflow_hint = (
                "Required workflow outline for this request: case_lookup -> policy_checker. "
                "Include both exactly once so the policy result determines whether human review is required."
            )
        prompt=f"""You are a plan generator, not a tool executor. Return JSON only.
User request: {request}
Detected entity literals: {entity_rules}
{workflow_hint}
Available tool contracts: {json.dumps(self.tools,indent=2)}
Rules:
- Select the smallest set of tools directly requested by the user. Never add unrelated policy, refund, report, response, or history tools.
- Every case_id or customer_id input MUST use the matching detected literal above. Never use a reference such as $task_id for case_id or customer_id.
- $task_id is valid only for an input field literally named task_id.
- task_id and all workflow metadata are system-controlled. Use $task_id as a non-authoritative placeholder only; never invent task IDs, approval IDs, database IDs, timestamps, report paths, or filenames.
- A case-based operation starts with case_lookup. Priority plus SLA uses case_lookup, then priority_classifier, then sla_checker.
- A case-based refund workflow must include customer_lookup after case_lookup, using customer_id=$case_lookup.customer_id, before policy_checker and refund_calculator.
- A refund calculation must run after policy_checker and must reference its outputs: amount_paid=$policy_checker.amount_paid, refund_percentage=$policy_checker.recommended_refund_percentage, non_refundable_fee=$policy_checker.non_refundable_fee, previous_refund_amount=$policy_checker.previous_refund_amount. Never invent these values.
- When a refund workflow requests a customer response, include generate_report before generate_customer_response; both use task_id=$task_id and require approval.
- Dependencies must point only to earlier step IDs. Use $tool_name.field only when a later input needs an earlier output (for example, sla_checker priority is $priority_classifier.priority).
- Use exact tool names and exact input field names from the tool contracts.
- Each inputs object maps an input field directly to its scalar value or $tool.field reference. Never wrap an input in an object such as {{"value": ...}}.
- Maximum 8 steps. Tools whose contract says requires_approval=true must require approval. A customer response requires approval only when the plan also calculates a refund; a response-only draft does not.
- Include concise public descriptions and reasons; never include hidden reasoning.
Required JSON Schema:\n{schema}"""
        raw=generate_text(self.provider,prompt,self.api_key,self.model,output_schema=plan_schema)
        try:
            return ExecutionPlan.model_validate(_single_json_object(raw))
        except Exception as exc:
            raise PlannerResponseError("The LLM returned an invalid execution plan.", self.provider, str(exc)) from exc
