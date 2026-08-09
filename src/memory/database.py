from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.config import DB_PATH, ensure_directories


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS customers (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, account_status TEXT NOT NULL,
  subscription_plan TEXT NOT NULL, tier TEXT NOT NULL, join_date TEXT NOT NULL,
  previous_refund_count INTEGER NOT NULL, open_case_count INTEGER NOT NULL,
  contact_preference TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, amount_paid TEXT NOT NULL,
  purchase_date TEXT, usage_percent TEXT, non_refundable_fee TEXT NOT NULL DEFAULT '0',
  previous_refund_amount TEXT NOT NULL DEFAULT '0', already_refunded INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(customer_id) REFERENCES customers(id)
);
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY, customer_id TEXT, order_id TEXT, case_type TEXT NOT NULL,
  description TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL,
  previous_contacts INTEGER NOT NULL, requested_resolution TEXT NOT NULL,
  customer_message TEXT NOT NULL,
  FOREIGN KEY(customer_id) REFERENCES customers(id), FOREIGN KEY(order_id) REFERENCES orders(id)
);
CREATE TABLE IF NOT EXISTS refund_policies (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sla_rules (priority TEXT PRIMARY KEY, hours INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, user_request TEXT NOT NULL, planner_mode TEXT NOT NULL,
  provider TEXT, status TEXT NOT NULL, plan_json TEXT, state_json TEXT,
  final_response TEXT, report_path TEXT, customer_response TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT
);
CREATE TABLE IF NOT EXISTS task_steps (
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, step_id TEXT NOT NULL,
  tool_name TEXT NOT NULL, description TEXT, reason TEXT, tool_input_json TEXT,
  tool_output_json TEXT, status TEXT NOT NULL, requires_approval INTEGER NOT NULL,
  started_at TEXT, completed_at TEXT, latency_ms INTEGER, error_message TEXT,
  UNIQUE(task_id, step_id), FOREIGN KEY(task_id) REFERENCES tasks(id)
);
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, step_id TEXT NOT NULL,
  decision TEXT NOT NULL, reason TEXT, decided_at TEXT NOT NULL,
  FOREIGN KEY(task_id) REFERENCES tasks(id)
);
CREATE TABLE IF NOT EXISTS tool_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, step_id TEXT,
  event_type TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL,
  FOREIGN KEY(task_id) REFERENCES tasks(id)
);
"""


class Database:
    def __init__(self, path: Path | str = DB_PATH) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        ensure_directories()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

