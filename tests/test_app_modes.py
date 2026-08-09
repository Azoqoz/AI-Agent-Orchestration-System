from pathlib import Path

import pytest

from src.agent.orchestrator import Orchestrator
from src.config import detect_app_mode
from src.memory.database import Database
from src.memory.seed import CASES, CUSTOMERS, seed_database
from src.ui.workspace import LLM_PROVIDERS, mode_presentation


def test_default_mode_is_local_when_app_mode_is_missing(tmp_path: Path) -> None:
    assert detect_app_mode(tmp_path / "missing.env", {}) == "local"


def test_dotenv_demo_mode_is_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_MODE", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("APP_MODE=demo\n", encoding="utf-8")
    assert detect_app_mode(env_file) == "demo"


def test_dotenv_local_mode_is_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_MODE", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("APP_MODE=local\n", encoding="utf-8")
    assert detect_app_mode(env_file) == "local"


def test_invalid_dotenv_mode_warns_and_falls_back_to_local(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_MODE=production\n", encoding="utf-8")
    with pytest.warns(RuntimeWarning, match="falling back to 'local'"):
        assert detect_app_mode(env_file, {}) == "local"


def test_host_environment_overrides_dotenv(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_MODE=demo\n", encoding="utf-8")
    assert detect_app_mode(env_file, {"APP_MODE": "local"}) == "local"


def test_demo_mode_hides_llm_configuration() -> None:
    presentation = mode_presentation("demo")
    assert presentation["planner_options"] == ("Offline / Deterministic",)
    assert presentation["show_planning_settings"] is False


def test_local_mode_retains_llm_and_provider_configuration() -> None:
    presentation = mode_presentation("local")
    assert presentation["planner_options"] == ("Offline / Deterministic", "LLM")
    assert presentation["show_planning_settings"] is True
    assert LLM_PROVIDERS == ("OpenAI", "Anthropic", "Gemini", "Ollama")


def test_demo_record_catalog_is_derived_from_seeded_repository(tmp_path: Path) -> None:
    database = Database(tmp_path / "catalog.db")
    seed_database(database)

    catalog = Orchestrator(database, app_mode="demo").repo.demo_record_catalog()

    assert catalog == {
        "customer_ids": sorted(customer[0] for customer in CUSTOMERS),
        "case_ids": sorted(case[0] for case in CASES),
    }


def test_demo_mode_rejects_llm_at_orchestration_boundary(tmp_path: Path) -> None:
    orchestrator = Orchestrator(Database(tmp_path / "demo.db"), app_mode="demo")
    with pytest.raises(ValueError, match="deterministic planning only"):
        orchestrator.start("Review CASE-220", planner_mode="llm", provider="openai")
    assert orchestrator.repo.search_tasks(limit=10) == []


def test_demo_mode_complete_workflow_needs_no_api_key_and_persists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    orchestrator = Orchestrator(Database(tmp_path / "demo.db"), app_mode="demo")
    waiting = orchestrator.start(
        "Review CASE-220, check eligibility, calculate the refund, and prepare a customer response."
    )
    assert waiting["planner_mode"] == "deterministic"
    assert waiting["provider"] is None
    assert waiting["status"] == "waiting_for_approval"

    completed = orchestrator.resume(waiting["task_id"], "approved", "Demo evidence reviewed")
    assert completed["status"] == "completed"
    assert completed["approval_status"] == "approved"
    assert completed["customer_response"]
    assert Path(completed["generated_report_path"]).exists()

    detail = orchestrator.repo.task_detail(completed["task_id"])
    assert detail is not None
    assert detail["status"] == "completed"
    assert detail["approvals"][0]["decision"] == "approved"
    assert orchestrator.repo.search_tasks(task_id=completed["task_id"], limit=10)[0]["id"] == completed["task_id"]
