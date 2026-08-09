import json

from src.agent.schemas import ExecutionPlan, PlanStep
from src.ui.components import planner_label


REQUEST = "Check customer CUST-104 and summarize all open cases."


def llm_plan(*steps: dict) -> str:
    return json.dumps({
        "task_type": "customer_operations",
        "planner_mode": "llm",
        "summary": "Check the requested customer.",
        "steps": list(steps),
    })


def customer_step(**overrides) -> dict:
    step = {
        "step_id": "step_1",
        "tool_name": "customer_lookup",
        "description": "Load customer",
        "reason": "Load the requested customer.",
        "inputs": {"customer_id": "CUST-104"},
    }
    step.update(overrides)
    return step


def mock_response(monkeypatch, response: str) -> None:
    monkeypatch.setattr("src.planners.llm_planner.generate_text", lambda *args, **kwargs: response)


def test_valid_llm_plan_executes_without_fallback(orchestrator, monkeypatch):
    mock_response(monkeypatch, llm_plan(customer_step()))
    state = orchestrator.start(REQUEST, planner_mode="llm", provider="ollama")

    assert state["status"] == "completed"
    assert state["requested_planner"] == "llm"
    assert state["executed_planner"] == "llm"
    assert state["fallback_used"] is False
    assert planner_label(state) == "LLM"


def test_invalid_ollama_json_uses_deterministic_fallback(orchestrator, monkeypatch):
    mock_response(monkeypatch, "{invalid json}")
    state = orchestrator.start(REQUEST, planner_mode="llm", provider="ollama")

    assert state["status"] == "completed"
    assert state["tool_results"]["customer_lookup"]["customer_id"] == "CUST-104"
    assert state["fallback_used"] is True
    assert state["executed_planner"] == "deterministic_fallback"
    assert planner_label(state) == "LLM → Deterministic fallback"
    assert state["planning_notice"] == "LLM planning could not produce a valid plan, so the deterministic planner was used."
    assert not state["errors"]


def test_unknown_llm_tool_uses_deterministic_fallback(orchestrator, monkeypatch):
    mock_response(monkeypatch, llm_plan(customer_step(tool_name="invented_tool")))
    state = orchestrator.start(REQUEST, planner_mode="llm", provider="ollama")

    assert state["status"] == "completed"
    assert state["fallback_used"] is True
    assert state["fallback_reason"] == "LLM plan failed validation."


def test_invalid_llm_dependency_uses_deterministic_fallback(orchestrator, monkeypatch):
    mock_response(monkeypatch, llm_plan(customer_step(depends_on=["missing_step"])))
    state = orchestrator.start(REQUEST, planner_mode="llm", provider="ollama")

    assert state["status"] == "completed"
    assert state["fallback_used"] is True
    assert [step["tool_name"] for step in state["plan"]["steps"]] == ["customer_lookup"]


def test_oversized_llm_plan_uses_deterministic_fallback(orchestrator, monkeypatch):
    steps = [customer_step(step_id=f"step_{index}") for index in range(9)]
    mock_response(monkeypatch, llm_plan(*steps))
    state = orchestrator.start(REQUEST, planner_mode="llm", provider="ollama")

    assert state["status"] == "completed"
    assert state["fallback_used"] is True
    assert len(state["plan"]["steps"]) == 1


def test_fallback_metadata_is_persisted_in_history(orchestrator, monkeypatch):
    mock_response(monkeypatch, "not json")
    state = orchestrator.start(REQUEST, planner_mode="llm", provider="ollama")
    persisted = orchestrator.repo.task_detail(state["task_id"])["state"]

    assert persisted["requested_planner"] == "llm"
    assert persisted["executed_planner"] == "deterministic_fallback"
    assert persisted["fallback_used"] is True
    assert persisted["fallback_reason"] == "LLM output was not a valid execution plan."
    assert persisted["planning_errors"]
    history_row = orchestrator.repo.search_tasks(task_id=state["task_id"], limit=1)[0]
    assert history_row["requested_planner"] == "llm"
    assert history_row["executed_planner"] == "deterministic_fallback"
    assert history_row["fallback_used"] is True


def test_unsupported_request_is_not_forced_through_fallback(orchestrator, monkeypatch):
    mock_response(monkeypatch, "not json")
    state = orchestrator.start("Tell me a joke", planner_mode="llm", provider="ollama")

    assert state["status"] == "failed"
    assert state["fallback_used"] is False
    assert not state["tool_results"]
    assert "either planner" in state["final_response"].lower()


def test_tool_execution_failure_does_not_trigger_fallback(orchestrator, monkeypatch):
    mock_response(monkeypatch, llm_plan(customer_step(
        tool_name="case_lookup",
        inputs={"case_id": "CASE-999"},
    )))
    state = orchestrator.start("Check CASE-999", planner_mode="llm", provider="ollama")

    assert state["status"] == "failed"
    assert state["fallback_used"] is False
    assert state["executed_planner"] == "llm"
    assert state["plan"]["steps"][0]["status"] == "failed"


def test_deterministic_mode_metadata_and_behavior_remain_unchanged(orchestrator):
    state = orchestrator.start(REQUEST, planner_mode="deterministic")

    assert state["status"] == "completed"
    assert state["requested_planner"] == "deterministic"
    assert state["executed_planner"] == "deterministic"
    assert state["fallback_used"] is False
    assert [step["tool_name"] for step in state["plan"]["steps"]] == ["customer_lookup"]


def test_invalid_deterministic_fallback_plan_fails_safely(orchestrator, monkeypatch):
    mock_response(monkeypatch, llm_plan(customer_step(tool_name="invented_tool")))
    invalid = ExecutionPlan(
        task_type="customer_operations",
        planner_mode="deterministic",
        summary="Invalid fallback",
        steps=[PlanStep(step_id="bad", tool_name="also_invented", description="bad", reason="bad")],
    )
    monkeypatch.setattr("src.agent.graph.DeterministicPlanner.create_plan", lambda self, request: invalid)

    state = orchestrator.start(REQUEST, planner_mode="llm", provider="ollama")

    assert state["status"] == "failed"
    assert state["fallback_used"] is True
    assert "neither planner" in state["final_response"].lower()


def test_fallback_respects_scoped_response_and_negative_refund_constraint(orchestrator, monkeypatch):
    request = "Review CASE-220 and prepare a customer response without calculating a refund."
    mock_response(monkeypatch, "invalid json")
    state = orchestrator.start(request, planner_mode="llm", provider="ollama")

    assert state["status"] == "completed"
    assert state["approval_status"] is None
    assert state["fallback_used"] is True
    assert [step["tool_name"] for step in state["plan"]["steps"]] == [
        "case_lookup", "customer_lookup", "generate_customer_response"
    ]
    assert "refund_calculator" not in state["tool_results"]
    assert state["generated_report_path"] is None
    assert state["customer_response"]


def test_valid_llm_plan_that_violates_negative_constraint_uses_scoped_fallback(orchestrator, monkeypatch):
    request = "Review CASE-220 and prepare a customer response without calculating a refund."
    response = llm_plan(
        {"step_id": "step_1", "tool_name": "case_lookup", "description": "Load case", "reason": "Context", "inputs": {"case_id": "CASE-220"}},
        {"step_id": "step_2", "tool_name": "customer_lookup", "description": "Load customer", "reason": "Context", "inputs": {"customer_id": "$case_lookup.customer_id"}, "depends_on": ["step_1"]},
        {"step_id": "step_3", "tool_name": "generate_report", "description": "Report", "reason": "Unrequested report", "inputs": {"task_id": "$task_id"}, "depends_on": ["step_2"], "requires_approval": True},
        {"step_id": "step_4", "tool_name": "generate_customer_response", "description": "Response", "reason": "Draft response", "inputs": {"task_id": "$task_id"}, "depends_on": ["step_3"]},
    )
    mock_response(monkeypatch, response)

    state = orchestrator.start(request, planner_mode="llm", provider="ollama")

    assert state["status"] == "completed"
    assert state["fallback_used"] is True
    assert [step["tool_name"] for step in state["plan"]["steps"]] == [
        "case_lookup", "customer_lookup", "generate_customer_response"
    ]
    assert "generate_report" not in state["tool_results"]
    assert state["approval_status"] is None
