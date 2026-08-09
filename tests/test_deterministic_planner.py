import pytest
from src.planners.deterministic import DeterministicPlanner, MISSING_REFUND_CASE_MESSAGE


def names(request: str) -> list[str]:
    return [s.tool_name for s in DeterministicPlanner().create_plan(request).steps]


def test_selects_refund_workflow():
    result=names("Review CASE-220, check eligibility, calculate the refund, and prepare a customer response")
    assert result == ["case_lookup","customer_lookup","policy_checker","refund_calculator","generate_report","generate_customer_response"]


@pytest.mark.parametrize("task_text", ["What is CASE-220?", "Review CASE-220."])
def test_generic_case_review_is_lookup_only(task_text):
    assert names(task_text) == ["case_lookup"]


def test_orders_dependencies():
    plan=DeterministicPlanner().create_plan("Determine priority and SLA status of CASE-225")
    assert [s.tool_name for s in plan.steps] == ["case_lookup","priority_classifier","sla_checker"]
    assert plan.steps[-1].depends_on == ["step_1","step_2"]


def test_removes_duplicate_intents():
    assert names("calculate calculate refund refund amount for CASE-220").count("refund_calculator") == 1


def test_refund_calculation_with_customer_only_requests_a_case_id():
    with pytest.raises(ValueError, match="A case ID is required") as error:
        DeterministicPlanner().create_plan("Calculate a refund for CUST-101.")

    assert str(error.value) == MISSING_REFUND_CASE_MESSAGE


def test_detects_customer_id():
    plan=DeterministicPlanner().create_plan("Check customer CUST-104 account")
    assert plan.steps[0].inputs["customer_id"] == "CUST-104"


def test_customer_open_cases_request_uses_customer_lookup_without_invalid_case_step():
    plan = DeterministicPlanner().create_plan("Check customer CUST-104 and summarize all open cases.")
    assert [step.tool_name for step in plan.steps] == ["customer_lookup"]
    assert plan.steps[0].inputs == {"customer_id": "CUST-104"}


def test_history_only_request():
    assert names("Show the most recent approved refund case") == ["task_history_search"]


def test_response_without_refund_uses_only_context_and_response():
    assert names("Review CASE-220 and prepare a customer response without calculating a refund.") == [
        "case_lookup", "customer_lookup", "generate_customer_response"
    ]


def test_internal_report_only_never_adds_customer_response():
    assert names("Review CASE-220, calculate the refund, and generate an internal report only.") == [
        "case_lookup", "customer_lookup", "policy_checker", "refund_calculator", "generate_report"
    ]


@pytest.mark.parametrize("task_text", [
    "Review CASE-220 and prepare a customer response without calculating a refund.",
    "Review CASE-220 and prepare a customer response; do not calculate the refund and no report.",
    "Review CASE-220 and prepare a customer response only.",
])
def test_negative_constraints_override_optional_refund_expansion(task_text):
    result = names(task_text)
    assert "refund_calculator" not in result
    assert "generate_report" not in result


def test_explicit_full_refund_workflow_keeps_calculation_audit_and_response():
    assert names("Review CASE-220, check eligibility, calculate the refund, and prepare a customer response") == [
        "case_lookup", "customer_lookup", "policy_checker", "refund_calculator", "generate_report", "generate_customer_response"
    ]


@pytest.mark.parametrize("task_text",["","Tell me a joke","calculate a refund"])
def test_rejects_unsupported_or_ambiguous(task_text):
    with pytest.raises(ValueError): DeterministicPlanner().create_plan(task_text)
