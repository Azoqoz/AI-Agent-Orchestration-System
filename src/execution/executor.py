from __future__ import annotations

import re
from typing import Any

from pydantic import TypeAdapter

from src.agent.schemas import CaseId, CustomerId, OrderId


_TOOL_REFERENCE = re.compile(r"^\$[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$")
_SYSTEM_INPUTS = {
    "generate_report": ("task_id",),
    "generate_customer_response": ("task_id",),
}
_ENTITY_PATTERNS = {
    "case_id": re.compile(r"\bCASE-\d{3,}\b", re.I),
    "customer_id": re.compile(r"\bCUST-\d{3,}\b", re.I),
    "order_id": re.compile(r"\bORD-\d{3,}\b", re.I),
}
_ENTITY_ADAPTERS = {
    "case_id": TypeAdapter(CaseId),
    "customer_id": TypeAdapter(CustomerId),
    "order_id": TypeAdapter(OrderId),
}
_TOOL_ENTITY_FIELDS = {
    "case_lookup": ("case_id", "customer_id"),
    "customer_lookup": ("customer_id",),
    "policy_checker": ("case_id",),
    "priority_classifier": ("case_id",),
    "sla_checker": ("case_id",),
    "task_history_search": ("case_id", "customer_id"),
}
_TOOL_OUTPUT_ENTITY_FIELDS = {
    "case_lookup": ("case_id", "customer_id", "order_id"),
    "customer_lookup": ("customer_id",),
}


def extract_request_entities(request: str) -> dict[str, str]:
    entities: dict[str, str] = {}
    for field, pattern in _ENTITY_PATTERNS.items():
        matches = {match.group(0).upper() for match in pattern.finditer(request)}
        if len(matches) == 1:
            entities[field] = _ENTITY_ADAPTERS[field].validate_python(matches.pop())
    return entities


def bind_tool_entities(context: dict[str, dict[str, str]] | None, tool_name: str, output: dict[str, Any]) -> dict[str, dict[str, str]]:
    current = context or {"request": {}, "resolved": {}}
    updated = {"request": dict(current.get("request", {})), "resolved": dict(current.get("resolved", {}))}
    for field in _TOOL_OUTPUT_ENTITY_FIELDS.get(tool_name, ()):
        adapter = _ENTITY_ADAPTERS[field]
        if field in output and output[field] not in (None, ""):
            updated["resolved"][field] = adapter.validate_python(output[field])
    return updated


def authoritative_entity(state: dict[str, Any], field: str) -> str | None:
    context = state.get("entity_context") or {"request": extract_request_entities(state.get("user_request", "")), "resolved": {}}
    return context.get("resolved", {}).get(field) or context.get("request", {}).get(field)


def apply_authoritative_inputs(inputs: dict[str, Any], state: dict[str, Any], tool_name: str | None) -> dict[str, Any]:
    if tool_name in _SYSTEM_INPUTS:
        return {"task_id": state["task_id"]}
    trusted = dict(inputs)
    for field in _TOOL_ENTITY_FIELDS.get(tool_name or "", ()):
        value = authoritative_entity(state, field)
        if value is not None:
            trusted[field] = value
    return trusted


def is_tool_reference(value: Any) -> bool:
    return isinstance(value, str) and (value == "$task_id" or bool(_TOOL_REFERENCE.fullmatch(value)))


def resolve_inputs(inputs: dict[str,Any], state: dict[str,Any], tool_name: str | None = None) -> dict[str,Any]:
    # These tools consume workflow identity exclusively from trusted AgentState.
    # Their planner-provided payload is intentionally ignored, including extras.
    inputs = apply_authoritative_inputs(inputs, state, tool_name)
    if tool_name in _SYSTEM_INPUTS:
        return inputs

    resolved={}
    for key,value in inputs.items():
        if not is_tool_reference(value):
            if value is not None: resolved[key]=value
            continue
        path=value[1:].split(".")
        if path[0] == "task_id": resolved[key]=state["task_id"]; continue
        source=state.get("tool_results",{}).get(path[0])
        if source is None: raise ValueError(f"Unresolved tool reference: {value}")
        current:Any=source
        for part in path[1:]: current=current[part]
        resolved[key]=current
    if tool_name == "refund_calculator":
        policy = state.get("tool_results", {}).get("policy_checker")
        if policy:
            resolved.update({
                "amount_paid": policy["amount_paid"],
                "refund_percentage": policy["recommended_refund_percentage"],
                "non_refundable_fee": policy.get("non_refundable_fee", "0"),
                "previous_refund_amount": policy.get("previous_refund_amount", "0"),
            })
    if tool_name == "sla_checker":
        priority = state.get("tool_results", {}).get("priority_classifier")
        if priority and priority.get("priority"):
            resolved["priority"] = priority["priority"]
    return resolved
