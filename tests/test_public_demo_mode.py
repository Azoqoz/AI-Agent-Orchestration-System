from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import build_service_container, get_service_container
from src.memory.database import Database
from src.services import InvalidTaskRequest, StartTaskRequest, TaskNotFound
from src.services.contracts import PlannerMode, ProviderName, TaskHistoryQuery
from src.services.demo import (
    DEMO_MAX_HISTORY_LIMIT,
    DEMO_MAX_REQUEST_LENGTH,
    DEMO_MAX_TASKS_PER_SESSION,
    GUIDED_DEMO_TASKS,
)


SESSION_A = "a" * 32
SESSION_B = "b" * 32


def _demo_services(database: Database, session_id: str):
    return build_service_container(database, app_mode="demo", session_id=session_id)


def _start(services, user_request: str):
    return services.tasks.start_task(StartTaskRequest(user_request=user_request))


def test_demo_capabilities_publish_guided_tasks_and_restrictions(tmp_path: Path) -> None:
    services = _demo_services(Database(tmp_path / "demo.db"), SESSION_A)
    application = create_app()
    application.dependency_overrides[get_service_container] = lambda: services

    with TestClient(application) as client:
        response = client.get("/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["app_mode"] == "demo"
    assert body["demo_mode_available"] is True
    assert body["free_form_task_policy"] == "supported_fictional_data"
    assert body["planner_modes"] == ["deterministic"]
    assert body["providers"] == []
    assert body["provider_controls_available"] is False
    assert body["provider_api_key_allowed"] is False
    assert body["history"] == {
        "scope": "demo_session",
        "max_results": DEMO_MAX_HISTORY_LIMIT,
        "retention_hours": 24,
    }
    assert [item["id"] for item in body["guided_demo_tasks"]] == [
        item.id for item in GUIDED_DEMO_TASKS
    ]
    assert [item["expected_tools"] for item in body["guided_demo_tasks"]] == [
        list(item.expected_tools) for item in GUIDED_DEMO_TASKS
    ]


def test_demo_dependency_requires_an_opaque_session_identifier(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.dependencies as dependencies

    monkeypatch.setattr(dependencies, "APP_MODE", "demo")
    with pytest.raises(InvalidTaskRequest, match="opaque session identifier"):
        dependencies.get_service_container(None)


@pytest.mark.parametrize(
    ("user_request", "provider", "model", "api_key", "message"),
    [
        ("Review CASE-220.", ProviderName.openai, None, None, "provider selection"),
        ("Review CASE-220.", None, "custom-model", None, "model selection"),
        ("Review CASE-220.", None, None, "must-not-be-used", "API keys"),
    ],
)
def test_demo_rejects_provider_model_and_api_key_inputs(
    tmp_path: Path,
    user_request: str,
    provider: ProviderName | None,
    model: str | None,
    api_key: str | None,
    message: str,
) -> None:
    services = _demo_services(Database(tmp_path / "demo.db"), SESSION_A)
    task_request = StartTaskRequest(
        user_request=user_request,
        planner_mode=PlannerMode.deterministic,
        provider=provider,
        model=model,
    )

    with pytest.raises(InvalidTaskRequest, match=message):
        services.tasks.start_task(task_request, api_key=api_key)
    assert services.history.search_tasks() == []


def test_demo_rejects_llm_before_task_creation(tmp_path: Path) -> None:
    services = _demo_services(Database(tmp_path / "demo.db"), SESSION_A)
    request = StartTaskRequest(
        user_request="Review CASE-220.",
        planner_mode=PlannerMode.llm,
        provider=ProviderName.openai,
    )

    with pytest.raises(InvalidTaskRequest, match="deterministic planning only"):
        services.tasks.start_task(request)
    assert services.history.search_tasks() == []


def test_demo_request_length_and_task_count_are_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _demo_services(Database(tmp_path / "demo.db"), SESSION_A)
    with pytest.raises(InvalidTaskRequest, match=str(DEMO_MAX_REQUEST_LENGTH)):
        _start(services, "x" * (DEMO_MAX_REQUEST_LENGTH + 1))

    monkeypatch.setattr(services.tasks.repo, "count_tasks", lambda: DEMO_MAX_TASKS_PER_SESSION)
    with pytest.raises(InvalidTaskRequest, match=str(DEMO_MAX_TASKS_PER_SESSION)):
        _start(services, "Review CASE-220.")


def test_demo_sessions_isolate_task_detail_history_events_and_approvals(tmp_path: Path) -> None:
    database = Database(tmp_path / "shared-demo.db")
    first = _demo_services(database, SESSION_A)
    second = _demo_services(database, SESSION_B)
    task = _start(first, GUIDED_DEMO_TASKS[0].user_request)

    assert [item.task_id for item in first.history.search_tasks()] == [task.task_id]
    assert second.history.search_tasks() == []
    for operation in (
        second.tasks.get_task,
        second.history.load_task_detail,
        second.history.events,
        second.history.approvals,
    ):
        with pytest.raises(TaskNotFound):
            operation(task.task_id)
    with pytest.raises(TaskNotFound):
        second.approvals.approve(task.task_id, "cross-session attempt")

    completed = first.approvals.approve(task.task_id, "session owner")
    assert completed.workflow.status.value == "completed"
    assert completed.approvals[0].reviewer_note == "session owner"


def test_task_history_search_only_reads_current_demo_session(tmp_path: Path) -> None:
    database = Database(tmp_path / "shared-demo.db")
    first = _demo_services(database, SESSION_A)
    second = _demo_services(database, SESSION_B)
    waiting = _start(first, GUIDED_DEMO_TASKS[0].user_request)
    completed = first.approvals.approve(waiting.task_id, "approved for session history")
    assert completed.workflow.status.value == "completed"

    first_search = _start(first, GUIDED_DEMO_TASKS[3].user_request)
    second_search = _start(second, GUIDED_DEMO_TASKS[3].user_request)
    first_payload = next(
        item.payload for item in first_search.tool_results if item.tool_name == "task_history_search"
    )
    second_payload = next(
        item.payload for item in second_search.tool_results if item.tool_name == "task_history_search"
    )

    assert first_payload["count"] == 1
    assert first_payload["tasks"][0]["id"] == completed.task_id
    assert second_payload["count"] == 0


@pytest.mark.parametrize("guided_index", [1, 2])
def test_non_approval_guided_demo_flows_use_expected_tools(
    tmp_path: Path,
    guided_index: int,
) -> None:
    services = _demo_services(Database(tmp_path / f"demo-{guided_index}.db"), SESSION_A)
    spec = GUIDED_DEMO_TASKS[guided_index]
    task = _start(services, spec.user_request)

    assert task.workflow.status.value == spec.expected_status
    assert [step.tool_name for step in task.plan.steps] == list(spec.expected_tools)


def test_refund_guided_demo_uses_real_approval_semantics(tmp_path: Path) -> None:
    services = _demo_services(Database(tmp_path / "approval.db"), SESSION_A)
    spec = GUIDED_DEMO_TASKS[0]
    waiting = _start(services, spec.user_request)

    assert waiting.workflow.status.value == "waiting_for_approval"
    assert [step.tool_name for step in waiting.plan.steps] == list(spec.expected_tools)
    assert waiting.pending_approval is not None
    approved = services.approvals.approve(waiting.task_id, "reviewed")
    assert approved.workflow.status.value == "completed"
    assert approved.generated_report_path
    assert approved.customer_response


def test_refund_guided_demo_rejection_keeps_report_and_skips_response(tmp_path: Path) -> None:
    services = _demo_services(Database(tmp_path / "rejection.db"), SESSION_A)
    waiting = _start(services, GUIDED_DEMO_TASKS[0].user_request)
    rejected = services.approvals.reject(waiting.task_id, "not approved")

    assert rejected.workflow.status.value == "rejected"
    assert rejected.generated_report_path
    assert rejected.customer_response is None
    assert [step.status.value for step in rejected.plan.steps[-2:]] == ["completed", "skipped"]


def test_guardrail_guided_demo_executes_no_tools(tmp_path: Path) -> None:
    services = _demo_services(Database(tmp_path / "guardrail.db"), SESSION_A)
    task = _start(services, GUIDED_DEMO_TASKS[4].user_request)

    assert task.workflow.status.value == "failed"
    assert task.plan is None
    assert task.tool_results == []
    assert task.pending_approval is None
    assert set(task.unsupported_actions) == {"execute refund", "send customer message"}
    assert services.history.search_tasks()[0].status.value == "failed"


def test_demo_history_limit_is_capped(tmp_path: Path) -> None:
    services = _demo_services(Database(tmp_path / "history.db"), SESSION_A)
    observed: dict[str, int] = {}

    def fake_search(**filters):
        observed["limit"] = filters["limit"]
        return []

    services.history.repo.search_tasks = fake_search
    services.history.search_tasks(TaskHistoryQuery(limit=50))
    assert observed["limit"] == DEMO_MAX_HISTORY_LIMIT


def test_local_mode_keeps_unscoped_persistence_and_provider_configuration(tmp_path: Path) -> None:
    database = Database(tmp_path / "local.db")
    first = build_service_container(database, app_mode="local")
    task = _start(first, GUIDED_DEMO_TASKS[1].user_request)
    second = build_service_container(database, app_mode="local")

    assert second.tasks.get_task(task.task_id).workflow.status.value == "completed"
    configuration = second.providers.configure(
        StartTaskRequest(
            user_request="Review CASE-220.",
            planner_mode=PlannerMode.llm,
            provider=ProviderName.openai,
        )
    )
    assert configuration.effective_provider == ProviderName.openai
    assert configuration.requires_api_key is True
