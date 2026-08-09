from pathlib import Path
import pytest

from src.agent.orchestrator import Orchestrator
from src.memory.database import Database


@pytest.fixture
def orchestrator(tmp_path: Path) -> Orchestrator:
    return Orchestrator(Database(tmp_path / "test.db"), app_mode="local")
