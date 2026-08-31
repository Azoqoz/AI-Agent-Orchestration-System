from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.orchestrator import Orchestrator
from src.agent.plan_validator import PlanValidationError, PlanValidator
from src.agent.schemas import (
    CaseLookupInput,
    CustomerLookupInput,
    ExecutionPlan,
    GenerateCustomerResponseInput,
    GenerateReportInput,
    PlanStep,
    PolicyCheckInput,
    PriorityClassifierInput,
    RefundCalculatorInput,
    SLACheckerInput,
    TaskHistorySearchInput,
)
from src.memory.database import Database
from src.planners.deterministic import DeterministicPlanner, UNSUPPORTED_ACTION_MESSAGE
from src.providers import ProviderError


def _tool_names(plan: ExecutionPlan | dict) -> list[str]:
    steps = plan.steps if isinstance(plan, ExecutionPlan) else plan["steps"]
    return [step.tool_name if isinstance(step, PlanStep) else step["tool_name"] for step in steps]


def _plan(*steps: PlanStep, planner_mode: str = "deterministic") -> ExecutionPlan:
    return ExecutionPlan(
        task_type="migration_parity",
        planner_mode=planner_mode,
        summary="Phase 1 migration parity plan",
        steps=list(steps),
    )


def _llm_case_lookup_plan() -> str:
    return json.dumps(
        {
            "task_type": "customer_operations",
            "planner_mode": "llm",
            "summary": "Review the requested case.",
            "steps": [
                {
                    "step_id": "step_1",
                    "tool_name": "case_lookup",
                    "description": "Review case",
                    "reason": "Load the referenced case facts.",
                    "inputs": {"case_id": "CASE-220"},
                    "depends_on": [],
                    "requires_approval": False,
                    "status": "pending",
                }
            ],
        }
    )


@pytest.mark.parametrize(
    ("task_text", "expected_tools"),
    [
        ("Check customer CUST-104 and summarize all open cases.", ["customer_lookup"]),
        ("Review CASE-220.", ["case_lookup"]),
        (
            "Calculate the refund amount for CASE-220.",
            ["case_lookup", "policy_checker", "refund_calculator"],
        ),
        (
            "Determine the priority and SLA status of CASE-225.",
            ["case_lookup", "priority_classifier", "sla_checker"],
        ),
        (
            "Review CASE-220 and generate an internal report only.",
            ["case_lookup", "customer_lookup", "generate_report"],
        ),
        ("Show the most recent approved refund case.", ["task_history_search"]),
    ],
)
def test_deterministic_planning_public_tool_order(task_text: str, expected_tools: list[str]) -> None:
    plan = DeterministicPlanner().create_plan(task_text)

    assert plan.planner_mode == "deterministic"
    assert _tool_names(plan) == expected_tools


@pytest.mark.parametrize(
    ("task_text", "unsupported_action"),
    [
        ("Execute a refund for CASE-220.", "execute refund"),
        ("Send an email to the customer for CASE-220.", "send email"),
        ("Update the customer record for CUST-101.", "modify customer"),
    ],
)
def test_unsupported_actions_fail_before_tool_execution(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
    task_text: str,
    unsupported_action: str,
) -> None:
    def unexpected_execution(*args, **kwargs):
        pytest.fail("Unsupported requests must be blocked before tool execution")

    monkeypatch.setattr(orchestrator.registry, "execute", unexpected_execution)

    state = orchestrator.start(task_text)

    assert state["status"] == "failed"
    assert state["failure_kind"] == "unsupported_action"
    assert state["unsupported_actions"] == [unsupported_action]
    assert state["plan"] == {}
    assert state["tool_results"] == {}
    assert state["final_response"] == UNSUPPORTED_ACTION_MESSAGE


def test_plan_validation_rejects_unknown_tool_and_invalid_input(orchestrator: Orchestrator) -> None:
    validator = PlanValidator(orchestrator.registry)
    unknown = PlanStep(step_id="unknown", tool_name="unknown_tool", description="Unknown", reason="Parity")
    missing_input = PlanStep(
        step_id="missing",
        tool_name="customer_lookup",
        description="Missing input",
        reason="Parity",
        inputs={},
    )

    with pytest.raises(PlanValidationError, match="Unknown tool"):
        validator.validate(_plan(unknown))
    with pytest.raises(PlanValidationError, match="missing required input: customer_id"):
        validator.validate(_plan(missing_input))


def test_plan_validation_rejects_later_dependency_and_cycles(orchestrator: Orchestrator) -> None:
    validator = PlanValidator(orchestrator.registry)
    first = PlanStep(
        step_id="first",
        tool_name="customer_lookup",
        description="First",
        reason="Parity",
        inputs={"customer_id": "CUST-101"},
        depends_on=["second"],
    )
    second = PlanStep(
        step_id="second",
        tool_name="case_lookup",
        description="Second",
        reason="Parity",
        inputs={"case_id": "CASE-220"},
        depends_on=["first"],
    )

    with pytest.raises(PlanValidationError, match="depends on a later step"):
        validator.validate(_plan(first, second))
    with pytest.raises(PlanValidationError, match="circular dependency"):
        validator._check_cycles(_plan(first, second))


def test_plan_validation_enforces_maximum_step_count(orchestrator: Orchestrator) -> None:
    steps = [
        PlanStep(
            step_id=f"step_{index}",
            tool_name="customer_lookup",
            description="Lookup customer",
            reason="Parity",
            inputs={"customer_id": "CUST-101"},
        )
        for index in range(9)
    ]

    with pytest.raises(PlanValidationError, match="8-step limit"):
        PlanValidator(orchestrator.registry).validate(_plan(*steps))


@pytest.mark.parametrize(
    ("tool_name", "inputs", "expected_inputs", "requires_approval"),
    [
        (
            "case_lookup",
            {"case_id": "CASE-999", "customer_id": "CUST-999"},
            {"case_id": "CASE-220", "customer_id": "CUST-101"},
            False,
        ),
        (
            "customer_lookup",
            {"customer_id": "CUST-999"},
            {"customer_id": "CUST-101"},
            False,
        ),
        (
            "generate_report",
            {"task_id": "TASK-FAKE"},
            {"task_id": "TASK-REAL"},
            True,
        ),
    ],
)
def test_plan_validation_enforces_trusted_identifiers(
    orchestrator: Orchestrator,
    tool_name: str,
    inputs: dict[str, str],
    expected_inputs: dict[str, str],
    requires_approval: bool,
) -> None:
    state = {
        "task_id": "TASK-REAL",
        "user_request": "Review CASE-220 for customer CUST-101.",
        "entity_context": {
            "request": {"case_id": "CASE-220", "customer_id": "CUST-101"},
            "resolved": {},
        },
    }
    step = PlanStep(
        step_id="trusted",
        tool_name=tool_name,
        description="Trusted identifiers",
        reason="Parity",
        inputs=inputs,
        requires_approval=requires_approval,
    )

    validated = PlanValidator(orchestrator.registry).validate(_plan(step), state)

    assert validated.steps[0].inputs == expected_inputs


def test_plan_validation_enforces_current_approval_rules(orchestrator: Orchestrator) -> None:
    validator = PlanValidator(orchestrator.registry)
    report = PlanStep(
        step_id="report",
        tool_name="generate_report",
        description="Generate report",
        reason="Parity",
        inputs={"task_id": "TASK-REAL"},
        requires_approval=False,
    )
    refund = PlanStep(
        step_id="refund",
        tool_name="refund_calculator",
        description="Calculate refund",
        reason="Parity",
        inputs={"amount_paid": "100", "refund_percentage": "100"},
    )
    response = PlanStep(
        step_id="response",
        tool_name="generate_customer_response",
        description="Draft response",
        reason="Parity",
        inputs={"task_id": "TASK-REAL"},
        depends_on=["refund"],
        requires_approval=False,
    )

    with pytest.raises(PlanValidationError, match="generate_report must require approval"):
        validator.validate(_plan(report))
    with pytest.raises(PlanValidationError, match="generate_customer_response must require approval"):
        validator.validate(_plan(refund, response))


@pytest.mark.parametrize(
    ("tool_name", "input_schema", "requires_approval"),
    [
        ("customer_lookup", CustomerLookupInput, False),
        ("case_lookup", CaseLookupInput, False),
        ("policy_checker", PolicyCheckInput, False),
        ("refund_calculator", RefundCalculatorInput, False),
        ("priority_classifier", PriorityClassifierInput, False),
        ("sla_checker", SLACheckerInput, False),
        ("generate_report", GenerateReportInput, True),
        ("generate_customer_response", GenerateCustomerResponseInput, False),
        ("task_history_search", TaskHistorySearchInput, False),
    ],
)
def test_registered_tool_contract_parity(
    orchestrator: Orchestrator,
    tool_name: str,
    input_schema: type,
    requires_approval: bool,
) -> None:
    definition = orchestrator.registry.get(tool_name)

    assert tool_name in orchestrator.registry.names()
    assert definition.input_schema is input_schema
    assert definition.requires_approval is requires_approval
    assert definition.output_schema is None


def test_deterministic_workflow_executes_persists_and_finalizes(orchestrator: Orchestrator) -> None:
    state = orchestrator.start("Determine the priority and SLA status of CASE-225.")

    assert state["status"] == "completed"
    assert _tool_names(state["plan"]) == ["case_lookup", "priority_classifier", "sla_checker"]
    assert state["tool_results"]["priority_classifier"]["priority"] == "High"
    assert state["tool_results"]["sla_checker"]["breached"] is True
    assert state["final_response"]

    persisted = orchestrator.repo.task_detail(state["task_id"])
    assert persisted is not None
    assert persisted["status"] == "completed"
    assert [step["status"] for step in persisted["steps"]] == ["completed", "completed", "completed"]


def test_approval_pause_is_persisted_and_approval_resumes_after_reconstruction(
    orchestrator: Orchestrator,
) -> None:
    waiting = orchestrator.start(
        "Review CASE-220, check eligibility, calculate the refund, and prepare a customer response."
    )

    assert waiting["status"] == "waiting_for_approval"
    assert waiting["plan"]["steps"][-2]["tool_name"] == "generate_report"
    assert waiting["plan"]["steps"][-2]["status"] == "waiting_for_approval"
    assert orchestrator.repo.get_task(waiting["task_id"])["status"] == "waiting_for_approval"

    reconstructed = Orchestrator(orchestrator.db, app_mode="local")
    assert reconstructed.load(waiting["task_id"])["status"] == "waiting_for_approval"

    completed = reconstructed.resume(waiting["task_id"], "approved", "Migration parity approval")
    detail = reconstructed.repo.task_detail(waiting["task_id"])

    assert completed["status"] == "completed"
    assert completed["approval_status"] == "approved"
    assert completed["generated_report_path"]
    assert completed["customer_response"]
    assert detail["approvals"][0]["decision"] == "approved"
    assert detail["approvals"][0]["reason"] == "Migration parity approval"


def test_rejection_preserves_current_audit_report_and_skips_customer_response(
    orchestrator: Orchestrator,
) -> None:
    waiting = orchestrator.start(
        "Review CASE-220, check eligibility, calculate the refund, and prepare a customer response."
    )

    rejected = Orchestrator(orchestrator.db, app_mode="local").resume(
        waiting["task_id"], "rejected", "Migration parity rejection"
    )
    detail = orchestrator.repo.task_detail(waiting["task_id"])

    assert rejected["status"] == "rejected"
    assert rejected["approval_status"] == "rejected"
    assert rejected["generated_report_path"]
    assert rejected["customer_response"] is None
    assert "no refund was approved or processed" in rejected["final_response"]
    assert detail["approvals"][0]["decision"] == "rejected"
    assert detail["plan_json"] is not None
    assert _tool_names(rejected["plan"])[-2:] == ["generate_report", "generate_customer_response"]
    assert rejected["plan"]["steps"][-2]["status"] == "completed"
    assert rejected["plan"]["steps"][-1]["status"] == "skipped"


def test_completed_task_memory_survives_new_orchestrator(orchestrator: Orchestrator) -> None:
    completed = orchestrator.start("Determine the priority and SLA status of CASE-225.")
    reconstructed = Orchestrator(orchestrator.db, app_mode="local")

    loaded = reconstructed.load(completed["task_id"])
    searched = reconstructed.repo.search_tasks(task_id=completed["task_id"], limit=10)
    tool_search = reconstructed.registry.execute(
        "task_history_search",
        {"task_id": completed["task_id"]},
        {"state": loaded},
    )

    assert loaded["status"] == "completed"
    assert loaded["tool_results"]["sla_checker"]["breached"] is True
    assert searched[0]["id"] == completed["task_id"]
    assert tool_search["count"] == 1
    assert tool_search["tasks"][0]["id"] == completed["task_id"]


def test_demo_mode_allows_deterministic_planning(tmp_path: Path) -> None:
    demo = Orchestrator(Database(tmp_path / "demo.db"), app_mode="demo")

    state = demo.start("Review CASE-220.")

    assert state["status"] == "completed"
    assert state["planner_mode"] == "deterministic"
    assert state["provider"] is None


def test_demo_mode_rejects_llm_before_task_creation(tmp_path: Path) -> None:
    demo = Orchestrator(Database(tmp_path / "demo.db"), app_mode="demo")

    with pytest.raises(ValueError, match="deterministic planning only"):
        demo.start("Review CASE-220.", planner_mode="llm", provider="openai")

    assert demo.repo.search_tasks(limit=10) == []


def test_local_mode_permits_mocked_llm_planner_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.planners.llm_planner.generate_text", lambda *args, **kwargs: _llm_case_lookup_plan())
    local = Orchestrator(Database(tmp_path / "local.db"), app_mode="local")

    state = local.start(
        "Review CASE-220.",
        planner_mode="llm",
        provider="openai",
        api_key="test-only-key",
        model="test-only-model",
    )

    assert state["status"] == "completed"
    assert state["requested_planner"] == "llm"
    assert state["executed_planner"] == "llm"
    assert state["provider"] == "openai"
    assert state["model"] == "test-only-model"


def test_malformed_llm_plan_falls_back_to_deterministic_without_network(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.planners.llm_planner.generate_text", lambda *args, **kwargs: "{invalid json")

    state = orchestrator.start(
        "Review CASE-220.",
        planner_mode="llm",
        provider="ollama",
        model="test-only-model",
    )

    assert state["status"] == "completed"
    assert state["requested_planner"] == "llm"
    assert state["executed_planner"] == "deterministic_fallback"
    assert state["fallback_used"] is True
    assert _tool_names(state["plan"]) == ["case_lookup"]


def test_mocked_provider_failure_preserves_current_failed_task_behavior(
    orchestrator: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def provider_failure(*args, **kwargs):
        raise ProviderError("mocked provider failure", "The configured provider is unavailable.")

    monkeypatch.setattr("src.planners.llm_planner.generate_text", provider_failure)

    state = orchestrator.start(
        "Review CASE-220.",
        planner_mode="llm",
        provider="openai",
        api_key="test-only-key",
    )

    assert state["status"] == "failed"
    assert state["display_error"] == "The configured provider is unavailable."
    assert state["fallback_used"] is False
    assert state["plan"] == {}
    assert state["tool_results"] == {}


def test_report_artifacts_and_persisted_path_use_only_isolated_directory(
    orchestrator: Orchestrator,
    isolated_report_dir: Path,
) -> None:
    waiting = orchestrator.start(
        "Review CASE-220, calculate the refund, and generate an internal report only."
    )
    completed = orchestrator.resume(waiting["task_id"], "approved", "Generate isolated report")

    markdown_path = Path(completed["generated_report_path"])
    text_path = markdown_path.with_suffix(".txt")
    persisted = orchestrator.repo.get_task(completed["task_id"])["state"]

    assert completed["status"] == "completed"
    assert markdown_path.parent == isolated_report_dir
    assert markdown_path.name == f"{completed['task_id']}.md"
    assert markdown_path.is_file()
    assert text_path.is_file()
    assert persisted["generated_report_path"] == str(markdown_path)
    assert markdown_path.parent != Path(__file__).resolve().parents[1] / "generated_reports"
