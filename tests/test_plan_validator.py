import pytest
from src.agent.plan_validator import PlanValidationError, PlanValidator
from src.agent.schemas import ExecutionPlan, PlanStep


def plan(steps): return ExecutionPlan(task_type="test",planner_mode="deterministic",summary="test",steps=steps)


def test_rejects_unknown_tool(orchestrator):
    with pytest.raises(PlanValidationError): PlanValidator(orchestrator.registry).validate(plan([PlanStep(step_id="a",tool_name="nope",description="x",reason="x")]))


def test_enforces_maximum(orchestrator):
    steps=[PlanStep(step_id=str(i),tool_name="customer_lookup",description="x",reason="x",inputs={"customer_id":"CUST-101"}) for i in range(9)]
    with pytest.raises(PlanValidationError): PlanValidator(orchestrator.registry).validate(plan(steps))


def test_rejects_invalid_dependency(orchestrator):
    step=PlanStep(step_id="a",tool_name="customer_lookup",description="x",reason="x",inputs={"customer_id":"CUST-101"},depends_on=["missing"])
    with pytest.raises(PlanValidationError): PlanValidator(orchestrator.registry).validate(plan([step]))


def test_rejects_later_dependency_and_cycle(orchestrator):
    a=PlanStep(step_id="a",tool_name="customer_lookup",description="x",reason="x",inputs={"customer_id":"CUST-101"},depends_on=["b"])
    b=PlanStep(step_id="b",tool_name="case_lookup",description="x",reason="x",inputs={"case_id":"CASE-220"},depends_on=["a"])
    with pytest.raises(PlanValidationError): PlanValidator(orchestrator.registry).validate(plan([a,b]))


def test_cycle_detector_rejects_circular_graph():
    a=PlanStep(step_id="a",tool_name="customer_lookup",description="x",reason="x",inputs={"customer_id":"CUST-101"},depends_on=["b"])
    b=PlanStep(step_id="b",tool_name="case_lookup",description="x",reason="x",inputs={"case_id":"CASE-220"},depends_on=["a"])
    with pytest.raises(PlanValidationError,match="circular"):
        PlanValidator._check_cycles(plan([a,b]))


def test_requires_sensitive_approval(orchestrator):
    step=PlanStep(step_id="a",tool_name="generate_report",description="x",reason="x",inputs={"task_id":"T"})
    with pytest.raises(PlanValidationError): PlanValidator(orchestrator.registry).validate(plan([step]))


def test_accepts_valid_plan(orchestrator):
    p=plan([PlanStep(step_id="a",tool_name="case_lookup",description="x",reason="x",inputs={"case_id":"CASE-220"})])
    assert PlanValidator(orchestrator.registry).validate(p).steps[0].tool_name == "case_lookup"
