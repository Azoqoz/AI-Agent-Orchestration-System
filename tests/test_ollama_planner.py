import json
import urllib.error

import pytest

from src.agent.plan_validator import PlanValidator
from src.execution.executor import resolve_inputs
from src.planners.llm_planner import LLMPlanner, PlannerResponseError
from src.providers import factory
from src.providers.factory import ProviderError
from src.ui.components import final_decision_fields
from src.ui.workspace import DEFAULT_OLLAMA_MODEL, provider_requires_api_key


def valid_plan_json() -> str:
    return json.dumps({
        "task_type": "customer_operations",
        "planner_mode": "llm",
        "summary": "Check priority and SLA.",
        "steps": [
            {
                "step_id": "step_1",
                "tool_name": "case_lookup",
                "description": "Load case",
                "reason": "Load the referenced case facts.",
                "inputs": {"case_id": "CASE-225"},
            },
            {
                "step_id": "step_2",
                "tool_name": "priority_classifier",
                "description": "Classify priority",
                "reason": "Assess urgency.",
                "inputs": {"case_id": "CASE-225"},
                "depends_on": ["step_1"],
            },
            {
                "step_id": "step_3",
                "tool_name": "sla_checker",
                "description": "Check SLA",
                "reason": "Compare elapsed time with the SLA.",
                "inputs": {"case_id": "CASE-225", "priority": "$priority_classifier.priority"},
                "depends_on": ["step_1", "step_2"],
            },
        ],
    })


def valid_refund_plan_json(task_id: str = "$task_id") -> str:
    return json.dumps({
        "task_type": "customer_operations",
        "planner_mode": "llm",
        "summary": "Review the case and prepare a refund response.",
        "steps": [
            {"step_id": "step_1", "tool_name": "case_lookup", "description": "Load case", "reason": "Load case facts.", "inputs": {"case_id": "CASE-220"}},
            {"step_id": "step_2", "tool_name": "customer_lookup", "description": "Load customer", "reason": "Load customer context.", "inputs": {"customer_id": "$case_lookup.customer_id"}, "depends_on": ["step_1"]},
            {"step_id": "step_3", "tool_name": "policy_checker", "description": "Check policy", "reason": "Apply refund policy.", "inputs": {"case_id": "CASE-220"}, "depends_on": ["step_1"]},
            {"step_id": "step_4", "tool_name": "refund_calculator", "description": "Calculate refund", "reason": "Calculate from policy outputs.", "inputs": {"amount_paid": "$policy_checker.amount_paid", "refund_percentage": "$policy_checker.recommended_refund_percentage", "non_refundable_fee": "$policy_checker.non_refundable_fee", "previous_refund_amount": "$policy_checker.previous_refund_amount"}, "depends_on": ["step_3"]},
            {"step_id": "step_5", "tool_name": "generate_report", "description": "Generate report", "reason": "Create the internal report.", "inputs": {"task_id": task_id}, "depends_on": ["step_4"], "requires_approval": True},
            {"step_id": "step_6", "tool_name": "generate_customer_response", "description": "Prepare response", "reason": "Prepare the customer response.", "inputs": {"task_id": task_id}, "depends_on": ["step_5"], "requires_approval": True},
        ],
    })


def planner_with_response(monkeypatch: pytest.MonkeyPatch, response: str) -> LLMPlanner:
    monkeypatch.setattr("src.planners.llm_planner.generate_text", lambda *args, **kwargs: response)
    return LLMPlanner("ollama", {}, model=DEFAULT_OLLAMA_MODEL)


def test_valid_ollama_structured_plan_still_passes_plan_validator(orchestrator, monkeypatch):
    plan = planner_with_response(monkeypatch, valid_plan_json()).create_plan(
        "Determine the priority and SLA status of CASE-225."
    )

    validated = PlanValidator(orchestrator.registry).validate(plan)
    assert [step.tool_name for step in validated.steps] == ["case_lookup", "priority_classifier", "sla_checker"]


def test_valid_ollama_plan_executes_end_to_end(orchestrator, monkeypatch):
    calls = []

    def generate(*args, **kwargs):
        calls.append((args, kwargs))
        return valid_plan_json()

    monkeypatch.setattr("src.planners.llm_planner.generate_text", generate)
    state = orchestrator.start(
        "Determine the priority and SLA status of CASE-225.",
        planner_mode="llm",
        provider="ollama",
        model=DEFAULT_OLLAMA_MODEL,
    )

    fields = dict(final_decision_fields(state))
    assert state["status"] == "completed"
    assert {"priority_classifier", "sla_checker"} <= state["tool_results"].keys()
    assert fields["Priority"] == "High" and fields["SLA status"] == "Breached"
    assert calls[0][0][3] == DEFAULT_OLLAMA_MODEL
    assert calls[0][1]["output_schema"]["title"] == "ExecutionPlan"


def test_ollama_generated_refund_workflow_resolves_policy_values(orchestrator, monkeypatch):
    monkeypatch.setattr("src.planners.llm_planner.generate_text", lambda *args, **kwargs: valid_refund_plan_json())
    state = orchestrator.start(
        "Review CASE-220, check eligibility, calculate the refund, and prepare a customer response.",
        planner_mode="llm",
        provider="ollama",
        model=DEFAULT_OLLAMA_MODEL,
    )

    assert state["status"] == "waiting_for_approval"
    assert state["tool_results"]["refund_calculator"]["final_recommended_refund"] == "115.00"
    refund_step = next(step for step in state["plan"]["steps"] if step["tool_name"] == "refund_calculator")
    assert refund_step["inputs"] == {
        "amount_paid": "120.00",
        "refund_percentage": "100",
        "non_refundable_fee": "5.00",
        "previous_refund_amount": "0",
    }


def test_case_lookup_binds_related_entities_and_overrides_planner_conflicts(orchestrator, monkeypatch):
    plan = json.loads(valid_refund_plan_json())
    next(step for step in plan["steps"] if step["tool_name"] == "case_lookup")["inputs"]["case_id"] = "CASE-999"
    next(step for step in plan["steps"] if step["tool_name"] == "customer_lookup")["inputs"]["customer_id"] = "CUST-999"
    next(step for step in plan["steps"] if step["tool_name"] == "policy_checker")["inputs"]["case_id"] = "CUST-101"
    monkeypatch.setattr("src.planners.llm_planner.generate_text", lambda *args, **kwargs: json.dumps(plan))

    state = orchestrator.start(
        "Review CASE-220, check eligibility, calculate the refund, and prepare a customer response.",
        planner_mode="llm",
        provider="ollama",
        model=DEFAULT_OLLAMA_MODEL,
    )

    steps = {step["tool_name"]: step for step in state["plan"]["steps"]}
    assert state["status"] == "waiting_for_approval"
    assert steps["case_lookup"]["inputs"]["case_id"] == "CASE-220"
    assert steps["customer_lookup"]["inputs"]["customer_id"] == "CUST-101"
    assert steps["policy_checker"]["inputs"]["case_id"] == "CASE-220"
    assert state["tool_results"]["customer_lookup"]["customer_id"] == "CUST-101"
    assert state["entity_context"] == {
        "request": {"case_id": "CASE-220"},
        "resolved": {"case_id": "CASE-220", "customer_id": "CUST-101", "order_id": "ORD-501"},
    }


def test_refund_resolution_prefers_completed_policy_outputs():
    state = {"tool_results": {"policy_checker": {
        "amount_paid": "120.00",
        "recommended_refund_percentage": "100",
        "non_refundable_fee": "5.00",
        "previous_refund_amount": "0.00",
    }}}
    invented = {
        "amount_paid": "$999.00",
        "refund_percentage": "12%",
        "non_refundable_fee": "unknown",
        "previous_refund_amount": "88 USD",
    }

    assert resolve_inputs(invented, state, "refund_calculator") == {
        "amount_paid": "120.00",
        "refund_percentage": "100",
        "non_refundable_fee": "5.00",
        "previous_refund_amount": "0.00",
    }


def test_sla_resolution_prefers_case_entity_and_classifier_output():
    state = {
        "entity_context": {"request": {"case_id": "CASE-225"}, "resolved": {"case_id": "CASE-225"}},
        "tool_results": {"priority_classifier": {"priority": "High"}},
    }

    assert resolve_inputs({"case_id": "CUST-104", "priority": "Low"}, state, "sla_checker") == {
        "case_id": "CASE-225",
        "priority": "High",
    }


@pytest.mark.parametrize("tool_name", ["generate_report", "generate_customer_response"])
def test_system_task_id_overrides_all_planner_inputs(tool_name):
    state = {"task_id": "TASK-AUTHORITATIVE"}
    planner_inputs = {
        "task_id": "TASK-FAKE",
        "approval_status": "approved",
        "report_path": "fake.md",
        "created_at": "never",
    }

    assert resolve_inputs(planner_inputs, state, tool_name) == {"task_id": "TASK-AUTHORITATIVE"}


def test_fake_llm_task_id_is_overridden_after_approval(orchestrator, monkeypatch):
    monkeypatch.setattr("src.planners.llm_planner.generate_text", lambda *args, **kwargs: valid_refund_plan_json("TASK-FAKE"))
    waiting = orchestrator.start(
        "Review CASE-220, check eligibility, calculate the refund, and prepare a customer response.",
        planner_mode="llm",
        provider="ollama",
        model=DEFAULT_OLLAMA_MODEL,
    )
    completed = orchestrator.resume(waiting["task_id"], "approved", "Evidence checked")

    assert completed["status"] == "completed"
    assert completed["approval_status"] == "approved"
    assert completed["generated_report_path"] and completed["customer_response"]
    assert "TASK-FAKE" not in completed["generated_report_path"]
    for tool_name in ("generate_report", "generate_customer_response"):
        step = next(step for step in completed["plan"]["steps"] if step["tool_name"] == tool_name)
        assert step["inputs"]["task_id"] == completed["task_id"]


def test_fake_llm_task_id_rejection_keeps_safe_audit_path(orchestrator, monkeypatch):
    monkeypatch.setattr("src.planners.llm_planner.generate_text", lambda *args, **kwargs: valid_refund_plan_json("TASK-FAKE"))
    waiting = orchestrator.start(
        "Review CASE-220, check eligibility, calculate the refund, and prepare a customer response.",
        planner_mode="llm",
        provider="ollama",
        model=DEFAULT_OLLAMA_MODEL,
    )
    rejected = orchestrator.resume(waiting["task_id"], "rejected", "Declined")

    assert rejected["status"] == "rejected"
    assert rejected["generated_report_path"]
    assert rejected["customer_response"] is None
    assert "no refund was approved or processed" in rejected["final_response"].lower()


def test_invalid_llm_refund_number_uses_deterministic_fallback(orchestrator, monkeypatch):
    plan = json.loads(valid_refund_plan_json())
    refund = next(step for step in plan["steps"] if step["tool_name"] == "refund_calculator")
    refund["inputs"] = {
        "amount_paid": "about one hundred dollars",
        "refund_percentage": "100%",
        "non_refundable_fee": "0",
        "previous_refund_amount": "0",
    }
    monkeypatch.setattr("src.planners.llm_planner.generate_text", lambda *args, **kwargs: json.dumps(plan))

    state = orchestrator.start("Calculate a refund for CASE-220", planner_mode="llm", provider="ollama")

    assert state["status"] == "completed"
    assert state["fallback_used"] is True
    assert state["executed_planner"] == "deterministic_fallback"
    assert "ConversionSyntax" not in state["final_response"]


def test_ollama_plan_wrapped_in_markdown_fences(monkeypatch):
    plan = planner_with_response(monkeypatch, f"```json\n{valid_plan_json()}\n```").create_plan("test")
    assert plan.steps[-1].tool_name == "sla_checker"


def test_ollama_plan_with_trailing_explanation(monkeypatch):
    plan = planner_with_response(monkeypatch, valid_plan_json() + "\nThis plan checks the requested case.").create_plan("test")
    assert plan.task_type == "customer_operations"


@pytest.mark.parametrize("response", ["{not json}", '{}\n{}', "There is no plan here"])
def test_malformed_or_ambiguous_ollama_plan_has_friendly_error(monkeypatch, response):
    with pytest.raises(PlannerResponseError) as error:
        planner_with_response(monkeypatch, response).create_plan("test")
    assert error.value.user_message == "Ollama returned an invalid execution plan. Please retry or use Deterministic Planner."


def test_malformed_plan_falls_back_without_exposing_parser_detail(orchestrator, monkeypatch):
    monkeypatch.setattr("src.planners.llm_planner.generate_text", lambda *args, **kwargs: "{not json}")
    state = orchestrator.start("Check CASE-225", planner_mode="llm", provider="ollama", model=DEFAULT_OLLAMA_MODEL)

    assert state["status"] == "completed"
    assert state["fallback_used"] is True
    assert state["display_error"] is None
    assert state["planning_notice"]
    assert "property name" not in state["final_response"].lower()
    assert state["planning_errors"]  # Technical detail remains available in Execution Details.


def test_unavailable_ollama_server_has_friendly_error(monkeypatch):
    monkeypatch.setattr(factory.urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("refused")))
    with pytest.raises(ProviderError) as error:
        factory.generate_text("ollama", "plan", model=DEFAULT_OLLAMA_MODEL, output_schema={"type": "object"})
    assert error.value.user_message == "Could not connect to Ollama. Make sure Ollama is running locally."


def test_unavailable_ollama_does_not_crash_or_expose_technical_error(orchestrator, monkeypatch):
    monkeypatch.setattr(factory.urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("refused")))
    state = orchestrator.start(
        "Determine the priority and SLA status of CASE-225.",
        planner_mode="llm",
        provider="ollama",
        model=DEFAULT_OLLAMA_MODEL,
    )

    expected = "Could not connect to Ollama. Make sure Ollama is running locally."
    assert state["status"] == "failed"
    assert state["display_error"] == expected
    assert expected in state["final_response"]
    assert "urlopen error" not in state["final_response"]


def test_ollama_requires_no_api_key_and_enforces_schema_and_temperature(monkeypatch):
    requests = []

    class Response:
        def __init__(self, payload=b"{}"):
            self.payload = payload
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return self.payload

    def fake_urlopen(request, timeout):
        requests.append(request)
        if isinstance(request, str):
            return Response()
        return Response(json.dumps({"response": valid_plan_json()}).encode())

    monkeypatch.setattr(factory.urllib.request, "urlopen", fake_urlopen)
    schema = {"type": "object", "required": ["steps"]}
    result = factory.generate_text("ollama", "plan", api_key=None, model=DEFAULT_OLLAMA_MODEL, output_schema=schema)

    body = json.loads(requests[1].data)
    assert json.loads(result)["steps"]
    assert body["format"] == schema
    assert body["options"]["temperature"] == 0
    assert "Authorization" not in requests[1].headers
    assert provider_requires_api_key("Ollama") is False
