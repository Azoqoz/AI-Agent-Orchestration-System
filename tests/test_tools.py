from decimal import Decimal
import pytest
from pydantic import ValidationError

from src.agent.schemas import RefundCalculatorInput


def run(orchestrator,name,inputs): return orchestrator.registry.execute(name,inputs,{"state":{"task_id":"T","plan":{"steps":[]},"tool_results":{}}})


def test_customer_lookup(orchestrator):
    assert run(orchestrator,"customer_lookup",{"customer_id":"CUST-104"})["tier"] == "Platinum"


def test_unknown_customer(orchestrator):
        with pytest.raises(ValueError): run(orchestrator,"customer_lookup",{"customer_id":"CUST-999"})


def test_case_id_cannot_be_used_as_customer_id(orchestrator):
    with pytest.raises(ValidationError, match="customer_id"):
        run(orchestrator, "customer_lookup", {"customer_id": "CASE-220"})


def test_unknown_case(orchestrator):
        with pytest.raises(ValueError): run(orchestrator,"case_lookup",{"case_id":"CASE-999"})


def test_customer_id_cannot_be_used_as_case_id(orchestrator):
    with pytest.raises(ValidationError, match="case_id"):
        run(orchestrator, "policy_checker", {"case_id": "CUST-101"})


def test_case_customer_mismatch(orchestrator):
    with pytest.raises(ValueError): run(orchestrator,"case_lookup",{"case_id":"CASE-220","customer_id":"CUST-104"})


@pytest.mark.parametrize(("case_id","expected"),[("CASE-220","Eligible"),("CASE-221","Not Eligible"),("CASE-223","Manual Review"),("CASE-224","Not Eligible"),("CASE-229","Manual Review")])
def test_policy_branches(orchestrator,case_id,expected):
    assert run(orchestrator,"policy_checker",{"case_id":case_id})["eligibility"] == expected


def test_refund_decimal_calculation(orchestrator):
    result=run(orchestrator,"refund_calculator",{"amount_paid":"120.00","refund_percentage":"75","non_refundable_fee":"5.00","previous_refund_amount":"10.00"})
    assert result["final_recommended_refund"] == "75.00"


@pytest.mark.parametrize(("value", "expected"), [
    (115, Decimal("115")),
    ("115.00", Decimal("115.00")),
    ("$115.00", Decimal("115.00")),
    ("115 USD", Decimal("115")),
])
def test_refund_money_inputs_are_normalized(value, expected):
    parsed = RefundCalculatorInput(amount_paid=value, refund_percentage="100%")
    assert parsed.amount_paid == expected
    assert parsed.refund_percentage == Decimal("100")


def test_decimal_percentage_string_keeps_percentage_point_semantics():
    parsed = RefundCalculatorInput(amount_paid="115", refund_percentage="0.50")
    assert parsed.refund_percentage == Decimal("0.50")


@pytest.mark.parametrize("value", ["about one hundred dollars", "unknown", "", "115 dollars because policy allows it"])
def test_refund_rejects_invalid_numeric_strings(value):
    with pytest.raises(ValidationError, match="invalid|non-empty"):
        RefundCalculatorInput(amount_paid=value, refund_percentage="100")


def test_refund_rejects_missing_required_numeric_value():
    with pytest.raises(ValidationError, match="amount_paid"):
        RefundCalculatorInput(refund_percentage="100")


def test_priority_high(orchestrator):
    result=run(orchestrator,"priority_classifier",{"case_id":"CASE-225"})
    assert result["priority"] == "High" and len(result["reasons"]) >= 3


def test_sla_breach(orchestrator):
    result=run(orchestrator,"sla_checker",{"case_id":"CASE-225","priority":"High"})
    assert result["breached"] is True and result["remaining_hours"] < 0


def test_unknown_tool_never_executes(orchestrator):
    with pytest.raises(KeyError): run(orchestrator,"shell",{})


def test_report_task_id_guard_still_rejects_internal_misuse(orchestrator):
    state = {"task_id": "TASK-REAL", "plan": {"steps": []}, "tool_results": {}}
    with pytest.raises(ValueError, match="does not match workflow state"):
        orchestrator.registry.execute("generate_report", {"task_id": "TASK-FAKE"}, {"state": state})
