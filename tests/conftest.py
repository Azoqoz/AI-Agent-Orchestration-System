from pathlib import Path
import pytest

from src.agent.orchestrator import Orchestrator
from src.memory.database import Database
from src.reporting import report_builder


@pytest.fixture(autouse=True)
def isolated_report_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep every test-generated report outside the project workspace."""
    report_dir = tmp_path / "generated_reports"
    monkeypatch.setattr(report_builder, "REPORT_DIR", report_dir)
    return report_dir


@pytest.fixture
def orchestrator(tmp_path: Path) -> Orchestrator:
    return Orchestrator(Database(tmp_path / "test.db"), app_mode="local")
