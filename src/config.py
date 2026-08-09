from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
import warnings

from dotenv import dotenv_values, load_dotenv


VALID_APP_MODES = frozenset({"demo", "local"})
ROOT_DIR = Path(__file__).resolve().parent.parent
DOTENV_PATH = ROOT_DIR / ".env"


def _invalid_mode_warning(value: str | None) -> str | None:
    if value is None or value.strip().lower() in VALID_APP_MODES:
        return None
    return (
        f"Unsupported APP_MODE={value!r}; falling back to 'local'. "
        "Accepted values are 'demo' and 'local'."
    )


def normalize_app_mode(value: str | None) -> str:
    """Return a supported mode, falling back safely to full local mode."""
    mode = (value if value is not None else "local").strip().lower()
    if mode in VALID_APP_MODES:
        return mode
    warnings.warn(_invalid_mode_warning(value), RuntimeWarning, stacklevel=2)
    return "local"


def _mode_value(env_path: Path, environ: Mapping[str, str] | None) -> str | None:
    if environ is None:
        load_dotenv(dotenv_path=env_path, override=False)
        return os.getenv("APP_MODE")
    if "APP_MODE" in environ:
        return environ["APP_MODE"]
    if not env_path.is_file():
        return None
    value = dotenv_values(env_path).get("APP_MODE")
    return str(value) if value is not None else None


def detect_app_mode(env_path: Path = DOTENV_PATH, environ: Mapping[str, str] | None = None) -> str:
    """Resolve runtime environment, then .env, then the local default."""
    return normalize_app_mode(_mode_value(Path(env_path), environ))


_CONFIGURED_APP_MODE = _mode_value(DOTENV_PATH, None)
APP_MODE_WARNING = _invalid_mode_warning(_CONFIGURED_APP_MODE)
APP_MODE = normalize_app_mode(_CONFIGURED_APP_MODE)
IS_DEMO_MODE = APP_MODE == "demo"
IS_LOCAL_MODE = APP_MODE == "local"

DATA_DIR = ROOT_DIR / "data"
REPORT_DIR = ROOT_DIR / "generated_reports"
DB_PATH = DATA_DIR / "agent_operations.db"
MAX_PLAN_STEPS = 8
DEMO_NOW = "2026-01-15T12:00:00+00:00"


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
