from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import ServiceContainer, build_service_container, get_service_container
from src.memory.database import Database


APPROVAL_TASK = "Review CASE-220, check eligibility, calculate the refund, and prepare a customer response."


@pytest.fixture
def api_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, ServiceContainer]]:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ALLOW_CREDENTIALS", raising=False)
    services = build_service_container(Database(tmp_path / "api.db"), app_mode="local")
    application = create_app()
    application.dependency_overrides[get_service_container] = lambda: services
    with TestClient(application) as client:
        yield client, services


def _llm_case_plan() -> str:
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


def test_health_does_not_resolve_service_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ALLOW_CREDENTIALS", raising=False)
    application = create_app()

    def unexpected_services():
        pytest.fail("Health must not initialize application services")

    application.dependency_overrides[get_service_container] = unexpected_services
    with TestClient(application) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_capabilities_come_from_provider_service_and_tool_registry(api_client) -> None:
    client, _ = api_client

    response = client.get("/capabilities")
    body = response.json()

    assert response.status_code == 200
    assert body["app_mode"] == "local"
    assert body["planner_modes"] == ["deterministic", "llm"]
    assert {provider["name"] for provider in body["providers"]} == {
        "openai",
        "anthropic",
        "gemini",
        "ollama",
    }
    assert next(provider for provider in body["providers"] if provider["name"] == "openai")["default_model"] == "gpt-4.1-mini"
    assert {tool["name"] for tool in body["tools"]} == {
        "customer_lookup",
        "case_lookup",
        "policy_checker",
        "refund_calculator",
        "priority_classifier",
        "sla_checker",
        "generate_report",
        "generate_customer_response",
        "task_history_search",
    }
    assert body["approval_required_tools"] == ["generate_report"]
    assert "x-provider-api-key" not in response.text.lower()


def test_post_tasks_runs_deterministic_workflow_and_returns_completed_detail(api_client) -> None:
    client, _ = api_client

    response = client.post(
        "/tasks",
        json={"user_request": "Determine priority and SLA status of CASE-225."},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["workflow"]["status"] == "completed"
    assert [step["tool_name"] for step in body["plan"]["steps"]] == [
        "case_lookup",
        "priority_classifier",
        "sla_checker",
    ]
    assert next(result for result in body["tool_results"] if result["tool_name"] == "priority_classifier")["payload"]["priority"] == "High"


def test_waiting_task_and_pending_approval_endpoint(api_client) -> None:
    client, _ = api_client

    started = client.post("/tasks", json={"user_request": APPROVAL_TASK})
    task = started.json()
    pending = client.get(f"/tasks/{task['task_id']}/approval")

    assert started.status_code == 200
    assert task["workflow"]["status"] == "waiting_for_approval"
    assert pending.status_code == 200
    assert pending.json()["task_id"] == task["task_id"]
    assert pending.json()["tool_name"] == "generate_report"


def test_approve_flow_returns_completed_task_and_persists_decision(api_client, isolated_report_dir: Path) -> None:
    client, _ = api_client
    task_id = client.post("/tasks", json={"user_request": APPROVAL_TASK}).json()["task_id"]

    response = client.post(
        f"/tasks/{task_id}/approval",
        json={"decision": "approved", "reviewer_note": "API approval"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["workflow"]["status"] == "completed"
    assert body["approval_status"] == "approved"
    assert body["customer_response"]
    assert Path(body["generated_report_path"]).parent == isolated_report_dir
    assert body["approvals"][0]["reviewer_note"] == "API approval"


def test_reject_flow_preserves_report_and_skips_customer_response(api_client, isolated_report_dir: Path) -> None:
    client, _ = api_client
    task_id = client.post("/tasks", json={"user_request": APPROVAL_TASK}).json()["task_id"]

    response = client.post(
        f"/tasks/{task_id}/approval",
        json={"decision": "rejected", "reviewer_note": "API rejection"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["workflow"]["status"] == "rejected"
    assert body["approval_status"] == "rejected"
    assert body["customer_response"] is None
    assert Path(body["generated_report_path"]).parent == isolated_report_dir
    assert [step["status"] for step in body["plan"]["steps"][-2:]] == ["completed", "skipped"]


def test_task_detail_history_steps_events_and_approvals_endpoints(api_client) -> None:
    client, _ = api_client
    task_id = client.post("/tasks", json={"user_request": APPROVAL_TASK}).json()["task_id"]
    client.post(
        f"/tasks/{task_id}/approval",
        json={"decision": "approved", "reviewer_note": "Audit endpoint note"},
    )

    detail = client.get(f"/tasks/{task_id}")
    history = client.get("/tasks", params={"status": "completed", "case_id": "CASE-220", "limit": 10})
    steps = client.get(f"/tasks/{task_id}/steps")
    events = client.get(f"/tasks/{task_id}/events")
    approvals = client.get(f"/tasks/{task_id}/approvals")

    assert detail.status_code == 200 and detail.json()["task_id"] == task_id
    assert history.status_code == 200 and [item["task_id"] for item in history.json()] == [task_id]
    assert steps.status_code == 200 and steps.json()[-1]["tool_name"] == "generate_customer_response"
    assert events.status_code == 200
    assert {event["event_type"] for event in events.json()} >= {"task_received", "approval_received"}
    assert approvals.status_code == 200
    assert approvals.json() == [
        {
            "id": approvals.json()[0]["id"],
            "task_id": task_id,
            "step_id": approvals.json()[0]["step_id"],
            "decision": "approved",
            "reviewer_note": "Audit endpoint note",
            "decided_at": approvals.json()[0]["decided_at"],
        }
    ]


def test_unknown_task_returns_structured_404(api_client) -> None:
    client, _ = api_client

    response = client.get("/tasks/TASK-MISSING")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "task_not_found",
            "message": "Task TASK-MISSING was not found",
            "task_id": "TASK-MISSING",
            "retryable": False,
        }
    }


def test_invalid_approval_and_missing_pending_approval_return_structured_409(api_client) -> None:
    client, _ = api_client
    task_id = client.post("/tasks", json={"user_request": "Review CASE-220."}).json()["task_id"]

    pending = client.get(f"/tasks/{task_id}/approval")
    decision = client.post(
        f"/tasks/{task_id}/approval",
        json={"decision": "approved", "reviewer_note": "Too late"},
    )

    assert pending.status_code == 409
    assert pending.json()["error"]["code"] == "approval_required"
    assert decision.status_code == 409
    assert decision.json()["error"]["code"] == "invalid_approval"


def test_request_validation_uses_structured_error_contract(api_client) -> None:
    client, _ = api_client

    response = client.post(
        "/tasks/TASK-MISSING/approval",
        json={"decision": "maybe", "reviewer_note": "Invalid"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_task_request",
            "message": "Request validation failed.",
            "task_id": None,
            "retryable": False,
        }
    }


def test_demo_mode_rejects_llm_without_provider_network_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_provider(*args, **kwargs):
        pytest.fail("Demo mode must reject LLM planning before provider execution")

    monkeypatch.setattr("src.planners.llm_planner.generate_text", unexpected_provider)
    services = build_service_container(Database(tmp_path / "demo-api.db"), app_mode="demo")
    application = create_app()
    application.dependency_overrides[get_service_container] = lambda: services

    with TestClient(application) as client:
        response = client.post(
            "/tasks",
            json={"user_request": "Review CASE-220.", "planner_mode": "llm", "provider": "openai"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_task_request"
    assert services.history.search_tasks() == []


def test_provider_api_key_header_is_never_returned_or_persisted(
    api_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, services = api_client
    secret = "phase3-header-secret-that-must-not-leak"
    observed: dict[str, str | None] = {}

    def mocked_provider(provider, prompt, api_key=None, model=None, output_schema=None):
        observed["api_key"] = api_key
        return _llm_case_plan()

    monkeypatch.setattr("src.planners.llm_planner.generate_text", mocked_provider)

    response = client.post(
        "/tasks",
        headers={"X-Provider-API-Key": secret},
        json={
            "user_request": "Review CASE-220.",
            "planner_mode": "llm",
            "provider": "openai",
            "model": "test-only-model",
        },
    )
    body = response.json()
    persisted = services.tasks.repo.get_task(body["task_id"])

    assert response.status_code == 200
    assert observed["api_key"] == secret
    assert secret not in response.text
    assert "api_key" not in response.text.lower()
    assert secret not in persisted["state_json"]
    assert "api_key" not in persisted["state"]


def test_default_local_cors_allows_expected_origin_and_rejects_other_origins(api_client) -> None:
    client, _ = api_client
    allowed = client.options(
        "/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    disallowed = client.options(
        "/health",
        headers={"Origin": "https://example.invalid", "Access-Control-Request-Method": "GET"},
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-credentials" not in allowed.headers
    assert "access-control-allow-origin" not in disallowed.headers


def test_cors_never_combines_wildcard_origin_with_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")
    application = create_app()

    with TestClient(application) as client:
        response = client.options(
            "/health",
            headers={"Origin": "https://frontend.example", "Access-Control-Request-Method": "GET"},
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in response.headers
