import pytest

from src.planners.deterministic import DeterministicPlanner, UnsupportedActionError
from src.planners.llm_planner import LLMPlanner


UNSUPPORTED_MESSAGE = (
    "This action is not supported in V1. The agent can review customer/case data, evaluate policies, "
    "calculate recommendations, generate reports, and draft customer responses, but it cannot modify "
    "customer or case records or send external messages."
)


def assert_unsupported(state, action):
    assert state["status"] == "failed"
    assert state["failure_kind"] == "unsupported_action"
    assert action in state["unsupported_actions"]
    assert state["final_response"] == UNSUPPORTED_MESSAGE
    assert state["tool_results"] == {}
    assert (state.get("plan") or {}).get("steps", []) == []
    assert state["fallback_used"] is False


def test_delete_customer_is_unsupported_and_does_not_delete(orchestrator):
    before = orchestrator.repo.one("customers", "CUST-101")
    state = orchestrator.start("Delete customer CUST-101.")

    assert_unsupported(state, "delete customer")
    assert orchestrator.repo.one("customers", "CUST-101") == before


def test_send_email_is_unsupported_before_llm_or_fallback(orchestrator, monkeypatch):
    def provider_must_not_run(*args, **kwargs):
        raise AssertionError("LLM provider should not run for blocked actions")

    monkeypatch.setattr("src.planners.llm_planner.generate_text", provider_must_not_run)
    state = orchestrator.start(
        "Send an email to CUST-101 confirming the refund.",
        planner_mode="llm",
        provider="ollama",
    )

    assert_unsupported(state, "send email")


def test_execute_refund_is_an_unsupported_real_world_action(orchestrator):
    state = orchestrator.start("Execute the refund for CASE-220.")
    assert_unsupported(state, "execute refund")


@pytest.mark.parametrize(("task_text", "action"), [
    ("Close CASE-220.", "close case"),
    ("Reopen CASE-220.", "reopen case"),
    ("Update CASE-220.", "update case"),
    ("Modify CASE-220.", "modify case"),
    ("Change CASE-220 status.", "change case status"),
    ("Resolve CASE-220.", "resolve case"),
    ("Delete CASE-220.", "delete case"),
    ("Assign CASE-220 to an agent.", "assign case"),
    ("Reassign CASE-220.", "assign case"),
])
def test_case_mutations_are_unsupported(orchestrator, task_text, action):
    before = orchestrator.repo.one("cases", "CASE-220")

    state = orchestrator.start(task_text)

    assert_unsupported(state, action)
    assert "case records" in state["final_response"]
    assert orchestrator.repo.one("cases", "CASE-220") == before


def test_case_mutation_is_blocked_before_llm_or_fallback(orchestrator, monkeypatch):
    def provider_must_not_run(*args, **kwargs):
        raise AssertionError("LLM provider should not run for blocked case mutations")

    monkeypatch.setattr("src.planners.llm_planner.generate_text", provider_must_not_run)
    state = orchestrator.start("Close CASE-220.", planner_mode="llm", provider="ollama")

    assert_unsupported(state, "close case")


def test_llm_planner_directly_rejects_case_mutation(monkeypatch):
    def provider_must_not_run(*args, **kwargs):
        raise AssertionError("LLM provider should not run for blocked case mutations")

    monkeypatch.setattr("src.planners.llm_planner.generate_text", provider_must_not_run)
    with pytest.raises(UnsupportedActionError) as error:
        LLMPlanner("ollama", {}).create_plan("Reopen CASE-220.")

    assert error.value.unsupported_actions == ["reopen case"]


@pytest.mark.parametrize("task_text", ["Review CASE-220.", "What is CASE-220?"])
def test_read_only_case_requests_remain_supported(orchestrator, task_text):
    state = orchestrator.start(task_text)

    assert state["status"] == "completed"
    assert state["failure_kind"] is None
    assert [step["tool_name"] for step in state["plan"]["steps"]] == ["case_lookup"]
    assert state["tool_results"]["case_lookup"]["case_id"] == "CASE-220"


def test_mixed_review_and_email_request_reports_email_not_executed(orchestrator):
    state = orchestrator.start("Review CASE-220 and send an email to the customer.")

    assert_unsupported(state, "send email")
    assert "case_lookup" not in state["tool_results"]


def test_deterministic_planner_rejects_unsupported_action_directly():
    with pytest.raises(UnsupportedActionError, match="not supported in V1"):
        DeterministicPlanner().create_plan("Cancel order ORD-501.")


def test_normal_supported_workflow_remains_unchanged(orchestrator):
    state = orchestrator.start("Determine the priority and SLA status of CASE-225.")

    assert state["status"] == "completed"
    assert state["failure_kind"] is None
    assert [step["tool_name"] for step in state["plan"]["steps"]] == [
        "case_lookup", "priority_classifier", "sla_checker"
    ]
