from pathlib import Path

from src.planners.deterministic import MISSING_REFUND_CASE_MESSAGE


REQUEST="Review CASE-220, check eligibility, calculate the refund, and prepare a customer response"


def test_workflow_pauses_for_approval(orchestrator):
    state=orchestrator.start(REQUEST)
    assert state["status"] == "waiting_for_approval"
    assert state["plan"]["steps"][-2]["status"] == "waiting_for_approval"
    assert "refund_calculator" in state["tool_results"]


def test_approval_resumes_and_completes(orchestrator):
    waiting=orchestrator.start(REQUEST)
    state=orchestrator.resume(waiting["task_id"],"approved","Evidence checked")
    assert state["status"] == "completed"
    assert state["approval_status"] == "approved"
    assert state["customer_response"] and Path(state["generated_report_path"]).exists()
    assert orchestrator.repo.task_detail(state["task_id"])["approvals"][0]["decision"] == "approved"


def test_rejection_safe_path(orchestrator):
    waiting=orchestrator.start(REQUEST)
    state=orchestrator.resume(waiting["task_id"],"rejected","Policy exception declined")
    assert state["status"] == "rejected"
    assert state["customer_response"] is None
    assert "no refund was approved" in state["final_response"].lower()
    assert Path(state["generated_report_path"]).exists()


def test_task_and_steps_persist(orchestrator):
    state=orchestrator.start("Determine priority and SLA status of CASE-225")
    detail=orchestrator.repo.task_detail(state["task_id"])
    assert detail["status"] == "completed" and len(detail["steps"]) == 3
    assert all(step["status"] == "completed" for step in detail["steps"])


def test_history_search(orchestrator):
    state=orchestrator.start("Determine priority and SLA status of CASE-225")
    result=orchestrator.registry.execute("task_history_search",{"task_id":state["task_id"]},{"state":state})
    assert result["count"] == 1 and result["tasks"][0]["id"] == state["task_id"]


def test_waiting_task_recoverable_from_new_instance(orchestrator):
    waiting=orchestrator.start(REQUEST)
    from src.agent.orchestrator import Orchestrator
    recovered=Orchestrator(orchestrator.db)
    assert recovered.load(waiting["task_id"])["status"] == "waiting_for_approval"
    assert recovered.resume(waiting["task_id"],"approved")["status"] == "completed"


def test_invalid_id_fails_without_corrupting_history(orchestrator):
    state=orchestrator.start("Check priority of CASE-999")
    assert state["status"] == "failed"
    assert orchestrator.repo.get_task(state["task_id"])["status"] == "failed"


def test_customer_only_refund_request_fails_with_safe_case_id_guidance(orchestrator):
    state = orchestrator.start("Calculate a refund for CUST-101.")

    assert state["status"] == "failed"
    assert state["display_error"] == MISSING_REFUND_CASE_MESSAGE
    assert state["errors"] == [MISSING_REFUND_CASE_MESSAGE]
    assert state["tool_results"] == {}
    assert state["plan"] == {}
    assert "case_lookup" not in str(state)
    assert "KeyError" not in str(state)


def test_case_based_refund_request_keeps_normal_workflow(orchestrator):
    state = orchestrator.start("Calculate a refund for CASE-220.")

    assert state["status"] == "completed"
    assert [step["tool_name"] for step in state["plan"]["steps"]] == [
        "case_lookup", "policy_checker", "refund_calculator"
    ]
    assert state["tool_results"]["refund_calculator"]["final_recommended_refund"] == "115.00"


def test_invalid_generic_case_lookup_fails_safely(orchestrator):
    state = orchestrator.start("What is CASE-999?")

    assert state["status"] == "failed"
    assert state["tool_results"] == {}
    assert "was not found" in state["final_response"]


def test_generic_case_review_is_read_only_and_returns_a_summary(orchestrator):
    for request in ("What is CASE-220?", "Review CASE-220."):
        state = orchestrator.start(request)

        assert state["status"] == "completed"
        assert [step["tool_name"] for step in state["plan"]["steps"]] == ["case_lookup"]
        assert set(state["tool_results"]) == {"case_lookup"}
        assert state["approval_status"] is None
        assert state["generated_report_path"] is None
        assert state["customer_response"] is None
        assert "CASE-220 is an open refund case for customer CUST-101" in state["final_response"]
        assert "duplicate purchase" in state["final_response"]
        assert "$120.00" in state["final_response"]
        assert "7 days ago" in state["final_response"]
        assert "5%" in state["final_response"]


def test_response_only_workflow_completes_without_approval(orchestrator):
    state = orchestrator.start(
        "Review CASE-220 and prepare a customer response without calculating a refund."
    )

    assert state["status"] == "completed"
    assert state["approval_status"] is None
    assert [step["tool_name"] for step in state["plan"]["steps"]] == [
        "case_lookup", "customer_lookup", "generate_customer_response"
    ]
    assert all(step["requires_approval"] is False for step in state["plan"]["steps"])
    assert "refund_calculator" not in state["tool_results"]
    assert "generate_report" not in state["tool_results"]
    assert state["generated_report_path"] is None
    assert state["customer_response"]
    assert state["recommended_action"] is None
    assert "$0.00" not in state["customer_response"]
    assert "recommended refund" not in state["customer_response"].lower()

    from src.ui.components import final_decision_fields
    fields = dict(final_decision_fields(state))
    assert fields["Outcome"] == "Completed"
    assert fields["Customer ID"] == "CUST-101"
    assert fields["Case ID"] == "CASE-220"
    assert fields["Customer response ready"] == "Yes"
    assert "Recommended refund" not in fields
    assert "Approval decision" not in fields
    assert "Report generated" not in fields


def test_refund_internal_report_remains_approval_gated(orchestrator):
    state = orchestrator.start(
        "Review CASE-220, calculate the refund, and generate an internal report only."
    )

    assert state["status"] == "waiting_for_approval"
    assert [step["tool_name"] for step in state["plan"]["steps"]] == [
        "case_lookup", "customer_lookup", "policy_checker", "refund_calculator", "generate_report"
    ]
    report = state["plan"]["steps"][-1]
    assert report["requires_approval"] is True
